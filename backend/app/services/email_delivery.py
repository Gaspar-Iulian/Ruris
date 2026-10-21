from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models import EmailAttempt, EmailOutbox, Role, User
from app.services.audit import record_audit
from app.services.mail import LocalEmailDeliveryError, configured_transport, mail_settings, send_email, send_to_local_mailpit
from app.services.notifications import build_blocked_invoice_digests, build_overdue_digests
from app.services.receipt_notifications import build_buyer_receipt_digests, build_warehouse_receipt_digests
from app.services.notification_kinds import RECIPIENT_ROLES


def content_hash(message):
    data = {key: message[key] for key in ("to", "subject", "body")}
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def snapshot(delivery):
    return {"kind": delivery.kind, "transport": delivery.transport, "as_of": delivery.as_of.isoformat(),
            "recipient_user_id": delivery.recipient_user_id, "status": delivery.status,
            "attempt_count": delivery.attempt_count, "last_error": delivery.last_error,
            "next_attempt_at": delivery.next_attempt_at.astimezone(timezone.utc).isoformat() if delivery.next_attempt_at else None}


def audit_delivery(delivery, action, before=None):
    process = {"OVERDUE": "overdue_email", "BLOCKED_INVOICES": "blocked_invoice_email",
               "RECEIPT_BUYER": "buyer_receipt_email", "RECEIPT_WAREHOUSE": "warehouse_receipt_email"}[delivery.kind]
    record_audit(action=action, entity_type="email_outbox", entity_id=delivery.id,
                 actor_process=process + ("_local" if delivery.transport == "LOCAL_MAILPIT" else "_smtp"),
                 before=before, after=snapshot(delivery))


def queue_overdue_emails():
    return queue_digest(kind="OVERDUE", builder=build_overdue_digests)


def queue_blocked_invoice_emails():
    return queue_digest(kind="BLOCKED_INVOICES", builder=build_blocked_invoice_digests)


def queue_digest(*, kind, builder, transport="LOCAL_MAILPIT"):
    if kind not in RECIPIENT_ROLES or transport not in ("LOCAL_MAILPIT", "SMTP"):
        raise ValueError("Canalul de notificare nu este valid.")
    try:
        digest = builder()
        queued = 0
        for message in digest["messages"]:
            delivery_id = db.session.scalar(insert(EmailOutbox).values(
                kind=kind, transport=transport, as_of=date.fromisoformat(digest["as_of"]),
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
        required_role = RECIPIENT_ROLES.get(delivery.kind)
        if (required_role is None or user is None or not user.is_active or user.role != required_role or user.email != delivery.recipient_email
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
                   "message_id": f"<ruris-{delivery.kind.lower().replace('_', '-')}-{delivery.id}@example.test>"}
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
    return send_digest_local(kind="OVERDUE", builder=build_overdue_digests, queue=queue_overdue_emails, retry_delay_seconds=retry_delay_seconds)


def send_blocked_invoice_digests_local(*, retry_delay_seconds=0):
    return send_digest_local(kind="BLOCKED_INVOICES", builder=build_blocked_invoice_digests, queue=queue_blocked_invoice_emails, retry_delay_seconds=retry_delay_seconds)


def send_notification_digests_local(*, retry_delay_seconds=0):
    overdue = send_overdue_digests_local(retry_delay_seconds=retry_delay_seconds)
    blocked = send_blocked_invoice_digests_local(retry_delay_seconds=retry_delay_seconds)
    buyer = send_receipt_digests_local(kind="RECEIPT_BUYER", builder=build_buyer_receipt_digests, retry_delay_seconds=retry_delay_seconds)
    warehouse = send_receipt_digests_local(kind="RECEIPT_WAREHOUSE", builder=build_warehouse_receipt_digests, retry_delay_seconds=retry_delay_seconds)
    return combine_results([overdue, blocked, buyer, warehouse])


def combine_results(results):
    states = {}
    for result in results:
        for status, count in result["states"].items():
            states[status] = states.get(status, 0) + count
    return {"as_of": results[0]["as_of"], "states": states,
            **{key: sum(result[key] for result in results) for key in ("queued", "skipped_items", "sent", "retryable")}}


def send_receipt_digests_local(*, kind, builder, retry_delay_seconds=0):
    return send_digest_local(kind=kind, builder=builder, queue=lambda: queue_digest(kind=kind, builder=builder),
                             retry_delay_seconds=retry_delay_seconds)


def send_notification_digests(*, retry_delay_seconds=0):
    transport = configured_transport()
    mail_settings(transport)
    recover_stale_deliveries(transport)
    if transport == "LOCAL_MAILPIT":
        return send_notification_digests_local(retry_delay_seconds=retry_delay_seconds)
    channels = [("OVERDUE", build_overdue_digests), ("BLOCKED_INVOICES", build_blocked_invoice_digests),
                ("RECEIPT_BUYER", build_buyer_receipt_digests), ("RECEIPT_WAREHOUSE", build_warehouse_receipt_digests)]
    results = []
    for kind, builder in channels:
        results.append(send_digest(kind=kind, builder=builder, transport=transport, retry_delay_seconds=retry_delay_seconds,
            queue=lambda: queue_digest(kind=kind, builder=builder, transport=transport)))
    return combine_results(results)


def recover_stale_deliveries(transport):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    try:
        while True:
            stale = db.session.execute(select(EmailOutbox.id, EmailAttempt.id.label("attempt_id"))
                .join(EmailAttempt, EmailAttempt.outbox_id == EmailOutbox.id)
                .where(EmailOutbox.transport == transport, EmailOutbox.status == "SENDING", EmailAttempt.status == "SENDING",
                       EmailAttempt.attempt_number == EmailOutbox.attempt_count, EmailAttempt.started_at < cutoff)
                .order_by(EmailOutbox.id).limit(1).with_for_update(of=EmailOutbox, skip_locked=True)).first()
            if stale is None:
                db.session.commit()
                return
            finish_delivery({"delivery_id": stale.id, "attempt_id": stale.attempt_id}, status="UNKNOWN", error_code="WORKER_INTERRUPTED")
    except Exception:
        db.session.rollback()
        raise


def send_digest_local(*, kind, builder, queue, retry_delay_seconds=0):
    return send_digest(kind=kind, builder=builder, queue=queue, transport="LOCAL_MAILPIT", retry_delay_seconds=retry_delay_seconds)


def send_digest(*, kind, builder, queue, transport, retry_delay_seconds=0):
    if type(retry_delay_seconds) is not int or not 0 <= retry_delay_seconds <= 3600:
        raise ValueError("Intervalul de reincercare trebuie sa fie intre 0 si 3600 de secunde.")
    queued = queue()
    try:
        fresh = builder()
        fresh_messages = {message["recipient_user_id"]: message for message in fresh["messages"]}
        day = date.fromisoformat(queued["as_of"])
        ids = db.session.scalars(select(EmailOutbox.id).where(EmailOutbox.as_of == day, EmailOutbox.transport == transport, EmailOutbox.kind == kind)
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
            if transport == "LOCAL_MAILPIT":
                send_to_local_mailpit(claim["payload"])
            else:
                send_email(claim["payload"], transport=transport)
        except LocalEmailDeliveryError as error:
            status = "UNKNOWN" if error.delivery_unknown else "FAILED"
            finish_delivery(claim, status=status, error_code="SMTP_RESULT_UNKNOWN" if error.delivery_unknown else "SMTP_NOT_ACCEPTED",
                            retry_delay_seconds=retry_delay_seconds)
        else:
            finish_delivery(claim, status="SENT")
            sent += 1
    states = dict(db.session.execute(select(EmailOutbox.status, func.count()).where(EmailOutbox.as_of == day,
                                                                               EmailOutbox.transport == transport, EmailOutbox.kind == kind)
                                     .group_by(EmailOutbox.status)).all())
    retryable = db.session.scalar(select(func.count()).select_from(EmailOutbox).where(
        EmailOutbox.as_of == day, EmailOutbox.transport == transport, EmailOutbox.kind == kind,
        EmailOutbox.status.in_(("PENDING", "FAILED")), EmailOutbox.attempt_count < 3,
    ))
    return {**queued, "sent": sent, "states": states, "retryable": retryable}


def list_email_deliveries(*, limit=20):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Limita trebuie sa fie intre 1 si 100.")
    rows = db.session.execute(select(EmailOutbox.id, EmailOutbox.kind, EmailOutbox.as_of, EmailOutbox.recipient_user_id, EmailOutbox.status,
                                      EmailOutbox.attempt_count, EmailOutbox.last_error, EmailOutbox.next_attempt_at)
                              .order_by(EmailOutbox.id.desc()).limit(limit))
    return [dict(row._mapping) for row in rows]
