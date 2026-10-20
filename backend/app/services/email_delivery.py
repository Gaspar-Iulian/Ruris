from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models import EmailAttempt, EmailOutbox, Role, User
from app.services.audit import record_audit
from app.services.mail import LocalEmailDeliveryError, send_to_local_mailpit
from app.services.notifications import build_overdue_digests


def content_hash(message):
    data = {key: message[key] for key in ("to", "subject", "body")}
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def snapshot(delivery):
    return {"kind": delivery.kind, "transport": delivery.transport, "as_of": delivery.as_of.isoformat(),
            "recipient_user_id": delivery.recipient_user_id, "status": delivery.status,
            "attempt_count": delivery.attempt_count, "last_error": delivery.last_error,
            "next_attempt_at": delivery.next_attempt_at.astimezone(timezone.utc).isoformat() if delivery.next_attempt_at else None}


def audit_delivery(delivery, action, before=None):
    record_audit(action=action, entity_type="email_outbox", entity_id=delivery.id,
                 actor_process="overdue_email_local", before=before, after=snapshot(delivery))


def queue_overdue_emails():
    try:
        digest = build_overdue_digests()
        queued = 0
        for message in digest["messages"]:
            delivery_id = db.session.scalar(insert(EmailOutbox).values(
                kind="OVERDUE", transport="LOCAL_MAILPIT", as_of=date.fromisoformat(digest["as_of"]),
                recipient_user_id=message["recipient_user_id"], recipient_email=message["to"], subject=message["subject"],
                body=message["body"], content_hash=content_hash(message), status="PENDING", attempt_count=0,
            ).on_conflict_do_nothing(constraint="uq_email_outbox_daily").returning(EmailOutbox.id))
            if delivery_id is not None:
                audit_delivery(db.session.get(EmailOutbox, delivery_id), "ENQUEUE")
                queued += 1
        db.session.commit()
        return {"as_of": digest["as_of"], "queued": queued, "skipped_items": digest["skipped_items"]}
    except Exception:
        db.session.rollback()
        raise


def claim_delivery(delivery_id, fresh_messages):
    try:
        delivery = db.session.scalar(select(EmailOutbox).where(EmailOutbox.id == delivery_id)
                                     .with_for_update(skip_locked=True).execution_options(populate_existing=True))
        if delivery is None or delivery.status not in {"PENDING", "FAILED"} or delivery.attempt_count >= 3:
            db.session.commit()
            return None
        if delivery.next_attempt_at is not None and delivery.next_attempt_at > datetime.now(timezone.utc):
            db.session.commit()
            return None
        user = db.session.scalar(select(User).where(User.id == delivery.recipient_user_id).execution_options(populate_existing=True))
        fresh = fresh_messages.get(delivery.recipient_user_id)
        before = snapshot(delivery)
        if (user is None or not user.is_active or user.role != Role.ACHIZITII or user.email != delivery.recipient_email
                or fresh is None or content_hash(fresh) != delivery.content_hash):
            delivery.status = "SKIPPED"
            delivery.last_error = "RECIPIENT_OR_DIGEST_CHANGED"
            delivery.next_attempt_at = None
            audit_delivery(delivery, "SKIP", before)
            db.session.commit()
            return None
        delivery.status = "SENDING"
        delivery.attempt_count += 1
        delivery.last_error = None
        delivery.next_attempt_at = None
        attempt = EmailAttempt(outbox_id=delivery.id, attempt_number=delivery.attempt_count, status="SENDING")
        db.session.add(attempt)
        db.session.flush()
        audit_delivery(delivery, "START", before)
        payload = {"to": delivery.recipient_email, "subject": delivery.subject, "body": delivery.body,
                   "message_id": f"<ruris-overdue-{delivery.id}@example.test>"}
        result = {"delivery_id": delivery.id, "attempt_id": attempt.id, "payload": payload}
        # Persist the claim before contacting SMTP.
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def finish_delivery(claim, *, status, error_code=None, retry_delay_seconds=0):
    if status not in {"SENT", "FAILED", "UNKNOWN"}:
        raise ValueError("Rezultatul trimiterii nu este valid.")
    try:
        delivery = db.session.scalar(select(EmailOutbox).where(EmailOutbox.id == claim["delivery_id"])
                                     .with_for_update().execution_options(populate_existing=True))
        attempt = db.session.get(EmailAttempt, claim["attempt_id"])
        if (delivery is None or attempt is None or attempt.outbox_id != delivery.id or delivery.status != "SENDING"
                or attempt.status != "SENDING" or delivery.attempt_count != attempt.attempt_number):
            raise ValueError("Starea jurnalului nu permite finalizarea acestei incercari.")
        before = snapshot(delivery)
        completed = datetime.now(timezone.utc)
        delivery.status = status
        delivery.last_error = error_code
        delivery.sent_at = completed if status == "SENT" else None
        delivery.next_attempt_at = (completed + timedelta(seconds=retry_delay_seconds)
                                    if status == "FAILED" and delivery.attempt_count < 3 else None)
        attempt.status = status
        attempt.error_code = error_code
        attempt.completed_at = completed
        audit_delivery(delivery, status, before)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def send_overdue_digests_local(*, retry_delay_seconds=0):
    if type(retry_delay_seconds) is not int or not 0 <= retry_delay_seconds <= 3600:
        raise ValueError("Intervalul de reincercare trebuie sa fie intre 0 si 3600 de secunde.")
    queued = queue_overdue_emails()
    try:
        fresh = build_overdue_digests()
        fresh_messages = {message["recipient_user_id"]: message for message in fresh["messages"]}
        day = date.fromisoformat(queued["as_of"])
        ids = db.session.scalars(select(EmailOutbox.id).where(EmailOutbox.as_of == day, EmailOutbox.transport == "LOCAL_MAILPIT")
                                 .order_by(EmailOutbox.id)).all()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    sent = 0
    for delivery_id in ids:
        claim = claim_delivery(delivery_id, fresh_messages)
        if claim is None:
            continue
        try:
            send_to_local_mailpit(claim["payload"])
        except LocalEmailDeliveryError as error:
            status = "UNKNOWN" if error.delivery_unknown else "FAILED"
            finish_delivery(claim, status=status, error_code="SMTP_RESULT_UNKNOWN" if error.delivery_unknown else "SMTP_NOT_ACCEPTED",
                            retry_delay_seconds=retry_delay_seconds)
        else:
            finish_delivery(claim, status="SENT")
            sent += 1
    states = dict(db.session.execute(select(EmailOutbox.status, func.count()).where(EmailOutbox.as_of == day,
                                                                               EmailOutbox.transport == "LOCAL_MAILPIT")
                                     .group_by(EmailOutbox.status)).all())
    retryable = db.session.scalar(select(func.count()).select_from(EmailOutbox).where(
        EmailOutbox.as_of == day, EmailOutbox.transport == "LOCAL_MAILPIT",
        EmailOutbox.status.in_(("PENDING", "FAILED")), EmailOutbox.attempt_count < 3,
    ))
    return {**queued, "sent": sent, "states": states, "retryable": retryable}


def list_email_deliveries(*, limit=20):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Limita trebuie sa fie intre 1 si 100.")
    rows = db.session.execute(select(EmailOutbox.id, EmailOutbox.as_of, EmailOutbox.recipient_user_id, EmailOutbox.status,
                                      EmailOutbox.attempt_count, EmailOutbox.last_error, EmailOutbox.next_attempt_at)
                              .order_by(EmailOutbox.id.desc()).limit(limit))
    return [dict(row._mapping) for row in rows]
