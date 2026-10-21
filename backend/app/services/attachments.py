import re

from sqlalchemy import func, select

from app.extensions import db
from app.models import Attachment, Invoice, PurchaseOrder, Receipt, Role, User
from app.services.attachment_storage import publish_attachment, read_attachment, stage_attachment, storage_directories
from app.services.audit import record_audit
from app.services.invoice_issues import invalidate_verification
from app.services.invoices import get_invoice, invoice_data
from app.services.purchase_orders import get_order, order_data, positive_id, visible_orders
from app.services.receipts import get_receipt, receipt_data, visible_receipts


MAX_ATTACHMENTS = 50
DOCUMENTS = {
    "orders": (PurchaseOrder, "purchase_order_id", Role.ACHIZITII, {Role.ACHIZITII, Role.CONTABILITATE}),
    "receipts": (Receipt, "receipt_id", Role.DEPOZIT, {Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE}),
    "invoices": (Invoice, "invoice_id", Role.CONTABILITATE, {Role.CONTABILITATE}),
}


class AttachmentForbidden(PermissionError):
    pass


class AttachmentNotFound(LookupError):
    pass


class AttachmentConflict(ValueError):
    pass


def check_role(kind, role, *, write=False):
    if kind not in DOCUMENTS:
        raise AttachmentNotFound("Documentul nu a fost gasit.")
    _, _, writer, readers = DOCUMENTS[kind]
    if role not in readers or write and role != writer:
        raise AttachmentForbidden("Rolul tau nu permite aceasta operatie asupra fisierelor documentului.")


def document_for(kind, document_id, role, *, write=False):
    check_role(kind, role, write=write)
    positive_id(document_id)
    model = DOCUMENTS[kind][0]
    conditions = visible_orders(role) if kind == "orders" else visible_receipts(role) if kind == "receipts" else []
    query = select(model).where(model.id == document_id, *conditions).execution_options(populate_existing=True)
    document = db.session.scalar(query.with_for_update() if write else query)
    if document is None:
        raise AttachmentNotFound("Documentul nu a fost gasit.")
    return document


def document_kind(record):
    for kind, (_, field, _, _) in DOCUMENTS.items():
        if getattr(record, field) is not None:
            return kind, getattr(record, field)
    raise AttachmentNotFound("Documentul nu a fost gasit.")


def document_data(kind, document, role):
    if kind == "orders":
        return get_order(document.id, role=role)
    if kind == "receipts":
        return get_receipt(document.id, role=role)
    return invoice_data(document)


def snapshot(document, kind):
    if kind == "orders":
        result = order_data(document, include_items=False)
    elif kind == "receipts":
        result = receipt_data(document, include_items=False)
    else:
        result = invoice_data(document, include_items=False)
    return {key: value for key, value in result.items() if key != "id"}


def attachment_data(record, *, include_names=False, names=None):
    result = {key: getattr(record, key) for key in (
        "id", "purchase_order_id", "receipt_id", "invoice_id", "original_name", "media_type", "size_bytes",
        "content_sha256", "upload_reason", "uploaded_by_id", "status", "withdrawn_by_id", "withdrawal_reason")}
    result["created_at"] = record.created_at.isoformat()
    result["withdrawn_at"] = record.withdrawn_at.isoformat() if record.withdrawn_at else None
    if include_names:
        result["uploaded_by_name"] = names.get(record.uploaded_by_id) if names is not None else db.session.scalar(select(User.name).where(User.id == record.uploaded_by_id))
        result["withdrawn_by_name"] = (names.get(record.withdrawn_by_id) if names is not None else db.session.scalar(select(User.name).where(User.id == record.withdrawn_by_id))) if record.withdrawn_by_id else None
    return result


def change_reason(reason):
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
        raise ValueError("Observatiile trebuie sa aiba intre 1 si 1000 de caractere.")
    return reason.strip()


def validate_version(version):
    if type(version) is not int or not 1 <= version < 2147483647:
        raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv sub 2147483647.")


def lock_actor(actor_user_id):
    actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
    if actor is None or not actor.is_active:
        raise AttachmentForbidden("Contul nu permite operatia.")
    return actor


def mutable(document, kind):
    states = {"DRAFT", "BLOCKED", "VERIFIED"} if kind == "invoices" else {"DRAFT", "CONFIRMED"}
    return document.status in states


def require_mutable(document, kind, version):
    if not mutable(document, kind) or document.version != version:
        raise AttachmentConflict("Documentul a fost modificat sau starea nu mai permite modificarea fisierelor. Reincarca documentul.")


def advance_document(document, kind, actor_id, reason):
    before = snapshot(document, kind)
    if kind == "invoices":
        invalidate_verification(document, actor_user_id=actor_id, reason=reason)
    document.version += 1
    entity = {"orders": "purchase_orders", "receipts": "receipts", "invoices": "invoices"}[kind]
    record_audit(action="UPDATE", entity_type=entity, entity_id=document.id, actor_user_id=actor_id,
                 before=before, after=snapshot(document, kind), reason=reason)


def list_attachments(kind, document_id, *, role, page, per_page):
    document = document_for(kind, document_id, role)
    field = getattr(Attachment, DOCUMENTS[kind][1])
    rows = db.session.scalars(select(Attachment).where(field == document.id)
        .order_by(Attachment.created_at.desc(), Attachment.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    user_ids = {value for row in rows for value in (row.uploaded_by_id, row.withdrawn_by_id) if value is not None}
    names = dict(db.session.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all())
    return {"attachments": [attachment_data(record, include_names=True, names=names) for record in rows],
            "total": db.session.scalar(select(func.count()).select_from(Attachment).where(field == document.id)),
            "page": page, "per_page": per_page, "document_version": document.version, "document_status": document.status,
            "can_manage": role == DOCUMENTS[kind][2] and mutable(document, kind), "max_file_bytes": 10 * 1024 * 1024,
            "max_attachments": MAX_ATTACHMENTS}


def upload_attachment(*, actor_user_id, kind, document_id, version, reason, upload_key, upload):
    published = None
    commit_started = False
    try:
        validate_version(version)
        reason = change_reason(reason)
        if not isinstance(upload_key, str) or not re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}", upload_key):
            raise ValueError("Cheia incarcarii trebuie sa fie un UUID v4 valid.")
        actor = lock_actor(actor_user_id)
        document = document_for(kind, document_id, actor.role, write=True)
        parent_field = DOCUMENTS[kind][1]
        with stage_attachment(upload) as staged:
            previous = db.session.scalar(select(Attachment).where(Attachment.uploaded_by_id == actor.id, Attachment.upload_key == upload_key))
            if previous is not None:
                fingerprint = (getattr(previous, parent_field), previous.original_name, previous.media_type, previous.size_bytes, previous.content_sha256, previous.upload_reason)
                expected = (document.id, staged.original_name, staged.media_type, staged.size_bytes, staged.content_sha256, reason)
                if fingerprint != expected:
                    raise AttachmentConflict("Cheia incarcarii a fost folosita pentru alt fisier sau alt document.")
                result = {"attachment": attachment_data(previous, include_names=True), "document": document_data(kind, document, actor.role), "replayed": True}
                db.session.commit()
                return result
            require_mutable(document, kind, version)
            total = db.session.scalar(select(func.count()).select_from(Attachment).where(getattr(Attachment, parent_field) == document.id))
            if total >= MAX_ATTACHMENTS:
                raise AttachmentConflict("Documentul are deja 50 de fisiere in istoric.")
            storage_key, published = publish_attachment(staged)
            record = Attachment(**{parent_field: document.id}, storage_key=storage_key, original_name=staged.original_name,
                media_type=staged.media_type, size_bytes=staged.size_bytes, content_sha256=staged.content_sha256,
                uploaded_by_id=actor.id, upload_key=upload_key, upload_reason=reason)
            db.session.add(record)
            db.session.flush()
            advance_document(document, kind, actor.id, reason)
            record_audit(action="UPLOAD", entity_type="attachments", entity_id=record.id, actor_user_id=actor.id,
                         after={key: value for key, value in attachment_data(record).items() if key != "id"}, reason=reason)
            result = {"attachment": attachment_data(record, include_names=True), "document": document_data(kind, document, actor.role), "replayed": False}
            commit_started = True
            db.session.commit()
            return result
    except Exception:
        db.session.rollback()
        if published is not None and not commit_started:
            published.unlink(missing_ok=True)
        # A failed commit may have succeeded remotely; retain its file for reconciliation.
        raise


def withdraw_attachment(*, actor_user_id, attachment_id, version, reason):
    try:
        positive_id(attachment_id)
        validate_version(version)
        reason = change_reason(reason)
        actor = lock_actor(actor_user_id)
        record = db.session.get(Attachment, attachment_id)
        if record is None:
            raise AttachmentNotFound("Fisierul nu a fost gasit.")
        kind, document_id = document_kind(record)
        document = document_for(kind, document_id, actor.role, write=True)
        require_mutable(document, kind, version)
        record = db.session.scalar(select(Attachment).where(Attachment.id == attachment_id).with_for_update().execution_options(populate_existing=True))
        if record.status != "ACTIVE":
            raise AttachmentConflict("Fisierul a fost deja retras. Reincarca documentele.")
        before = {key: value for key, value in attachment_data(record).items() if key != "id"}
        now = db.session.scalar(select(func.clock_timestamp()))
        record.status, record.withdrawal_reason, record.withdrawn_by_id, record.withdrawn_at = "WITHDRAWN", reason, actor.id, now
        advance_document(document, kind, actor.id, reason)
        db.session.flush()
        record_audit(action="WITHDRAW", entity_type="attachments", entity_id=record.id, actor_user_id=actor.id,
                     before=before, after={key: value for key, value in attachment_data(record).items() if key != "id"}, reason=reason)
        result = {"attachment": attachment_data(record, include_names=True), "document": document_data(kind, document, actor.role)}
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def download_attachment(*, actor_user_id, attachment_id):
    try:
        positive_id(attachment_id)
        actor = lock_actor(actor_user_id)
        record = db.session.get(Attachment, attachment_id)
        if record is None:
            raise AttachmentNotFound("Fisierul nu a fost gasit.")
        kind, document_id = document_kind(record)
        document_for(kind, document_id, actor.role)
        data = read_attachment(record)
        record_audit(action="DOWNLOAD", entity_type="attachments", entity_id=record.id, actor_user_id=actor.id,
                     after={key: value for key, value in attachment_data(record).items() if key != "id"})
        result = data, record.original_name, record.media_type
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def check_attachment_storage():
    rows = db.session.scalars(select(Attachment).order_by(Attachment.id)).all()
    objects, staging = storage_directories()
    result = {"referenced": len(rows), "missing_or_corrupted": 0, "unreferenced": 0, "staged": 0}
    for record in rows:
        try:
            read_attachment(record)
        except OSError:
            result["missing_or_corrupted"] += 1
    known = {record.storage_key for record in rows}
    if objects.exists():
        result["unreferenced"] = sum(path.name not in known for path in objects.iterdir())
    if staging.exists():
        result["staged"] = sum(1 for _ in staging.iterdir())
    return result
