from datetime import timedelta

from flask import render_template

from app.extensions import db
from app.models import Invoice, InvoiceIssue, PurchaseOrder, PurchaseOrderItem, Role, Supplier, User
from sqlalchemy import select
from app.services.purchase_orders import bucharest_date, overdue_items_query


def render_overdue_body(*, name, items, as_of):
    return render_template("emails/overdue_digest.txt", name=name, items=items, as_of=as_of).strip()


def build_test_overdue_message():
    today = bucharest_date()
    return {
        "to": "achizitii@example.com", "subject": f"[TEST] Ruris - sumar intarzieri - {today}",
        "body": render_overdue_body(name="Responsabil test", as_of=today.isoformat(), items=[{
            "order_number": "CA-DEMO", "line_number": 1, "description": "Produs demonstrativ",
            "unit": "BUC", "remaining_quantity": "7.000", "expected_date": (today - timedelta(days=1)).isoformat(), "days_overdue": 1,
        }]),
    }


def build_overdue_digests():
    today = bucharest_date()
    query = (
        overdue_items_query(today)
        .add_columns(User.id.label("recipient_id"), User.name.label("recipient_name"),
                     User.email.label("recipient_email"), User.role.label("recipient_role"), User.is_active.label("recipient_active"))
        .join(User, User.id == PurchaseOrder.owner_id)
        .order_by(User.id, PurchaseOrderItem.expected_date, PurchaseOrder.id, PurchaseOrderItem.line_number)
    )
    groups = {}
    skipped_items = 0
    for row in db.session.execute(query):
        if not row.recipient_active or row.recipient_role != Role.ACHIZITII:
            skipped_items += 1
            continue
        group = groups.setdefault(row.recipient_id, {
            "name": row.recipient_name, "email": row.recipient_email, "items": [],
        })
        group["items"].append({
            "order_number": row.order_number, "line_number": row.line_number,
            "description": row.description, "unit": row.unit,
            "remaining_quantity": format(row.remaining_quantity, ".3f"),
            "expected_date": row.expected_date.isoformat(), "days_overdue": (today - row.expected_date).days,
        })
    messages = []
    for user_id, group in groups.items():
        messages.append({
            "recipient_user_id": user_id, "to": group["email"],
            "subject": f"Ruris - sumar intarzieri - {today.isoformat()}",
            "body": render_overdue_body(name=group["name"], items=group["items"], as_of=today.isoformat()),
            "item_count": len(group["items"]),
        })
    return {"as_of": today.isoformat(), "timezone": "Europe/Bucharest", "messages": messages, "skipped_items": skipped_items}


def build_blocked_invoice_digests():
    today = bucharest_date()
    rows = db.session.execute(select(Invoice.id.label("invoice_id"), Invoice.series, Invoice.number, Invoice.invoice_date,
        Supplier.name.label("supplier_name"), InvoiceIssue.invoice_item_id, InvoiceIssue.code, InvoiceIssue.details,
        InvoiceIssue.responsible_role).join(InvoiceIssue, InvoiceIssue.invoice_id == Invoice.id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .where(Invoice.status == "BLOCKED", InvoiceIssue.resolved_at.is_(None))
        .order_by(Invoice.id, InvoiceIssue.id)).all()
    messages = []
    users = db.session.execute(select(User.id, User.name, User.email).where(User.is_active.is_(True), User.role == Role.CONTABILITATE).order_by(User.id)).all()
    if rows:
        items = [dict(row._mapping) for row in rows]
        for user in users:
            messages.append({"recipient_user_id": user.id, "to": user.email,
                "subject": f"Ruris - facturi blocate - {today.isoformat()}",
                "body": render_template("emails/blocked_invoices.txt", name=user.name, as_of=today.isoformat(), items=items).strip(),
                "item_count": len(items)})
    return {"as_of": today.isoformat(), "timezone": "Europe/Bucharest", "messages": messages,
            "skipped_items": len(rows) if not users else 0}
