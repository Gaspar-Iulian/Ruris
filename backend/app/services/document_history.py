from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.models import AuditEvent, InvoiceAllocation, InvoiceItem, Role, User
from app.services.invoices import InvoiceForbiddenError, get_invoice
from app.services.purchase_orders import get_order


def project_snapshot(column, fields):
    pairs = func.jsonb_each(column).table_valued("key", "value")
    projected = select(func.coalesce(func.jsonb_object_agg(pairs.c.key, pairs.c.value), literal({}, JSONB)))\
        .where(pairs.c.key.in_(fields)).correlate(AuditEvent).scalar_subquery()
    return case((column.is_(None), None), else_=projected)


def related_items(entity_type, parent_field, document_id):
    return and_(AuditEvent.entity_type == entity_type, or_(
        AuditEvent.before_data.contains({parent_field: document_id}),
        AuditEvent.after_data.contains({parent_field: document_id})))


def get_document_history(kind, document_id, *, role, page, per_page):
    if kind not in ("order", "invoice"):
        raise ValueError("Tip de document invalid.")
    if kind == "invoice" and role != Role.CONTABILITATE:
        raise InvoiceForbiddenError("Doar contabilitatea poate consulta istoricul facturilor.")
    if kind == "order":
        get_order(document_id, role=role)
        condition = or_(and_(AuditEvent.entity_type == "purchase_orders", AuditEvent.entity_id == document_id),
                        related_items("purchase_order_items", "purchase_order_id", document_id))
        if role != Role.DEPOZIT:
            condition = or_(condition, related_items("attachments", "purchase_order_id", document_id))
    else:
        get_invoice(document_id)
        line_ids = select(InvoiceItem.id).where(InvoiceItem.invoice_id == document_id)
        allocation_ids = select(InvoiceAllocation.id).where(InvoiceAllocation.invoice_item_id.in_(line_ids))
        condition = or_(and_(AuditEvent.entity_type == "invoices", AuditEvent.entity_id == document_id),
                        related_items("invoice_items", "invoice_id", document_id),
                        and_(AuditEvent.entity_type == "invoice_allocations", AuditEvent.entity_id.in_(allocation_ids)),
                        related_items("invoice_issues", "invoice_id", document_id))
        condition = or_(condition, related_items("attachments", "invoice_id", document_id))
    before, after, reason = AuditEvent.before_data, AuditEvent.after_data, AuditEvent.reason
    if role == Role.DEPOZIT:
        fields = ["number", "supplier_id", "status", "version", "confirmed_at", "purchase_order_id",
                  "line_number", "product_id", "description", "unit", "quantity", "expected_date"]
        before, after = project_snapshot(before, fields), project_snapshot(after, fields)
        # Purchasing notes may contain commercial values.
        reason = literal(None)
    rows = db.session.execute(select(AuditEvent.id, AuditEvent.entity_type, AuditEvent.entity_id, AuditEvent.action,
        AuditEvent.actor_user_id, User.name.label("actor_name"), AuditEvent.actor_process, AuditEvent.created_at,
        reason.label("reason"), before.label("before"), after.label("after"))
        .outerjoin(User, User.id == AuditEvent.actor_user_id).where(condition)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    line_ids = dict(db.session.execute(select(InvoiceItem.id, InvoiceItem.line_number)
        .where(InvoiceItem.invoice_id == document_id)).all()) if kind == "invoice" else {}
    events = []
    for row in rows:
        data = dict(row._mapping)
        snapshot = data["after"] or data["before"] or {}
        data["line_number"] = snapshot.get("line_number") or line_ids.get(snapshot.get("invoice_item_id"))
        data["actor_name"] = data["actor_name"] or data.pop("actor_process")
        data.pop("actor_process", None)
        data["created_at"] = row.created_at.isoformat()
        events.append(data)
    return {"events": events, "total": db.session.scalar(select(func.count()).select_from(AuditEvent).where(condition)),
            "page": page, "per_page": per_page}
