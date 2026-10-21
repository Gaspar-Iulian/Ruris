from decimal import Decimal

from flask import render_template
from sqlalchemy import func, select

from app.extensions import db
from app.models import Product, PurchaseOrder, PurchaseOrderItem, Receipt, ReceiptItem, Role, Supplier, User
from app.services.purchase_orders import accepted_quantities_subquery, bucharest_date


def pending_responsibilities():
    accepted = accepted_quantities_subquery()
    source_id = func.coalesce(ReceiptItem.pending_order_item_id, ReceiptItem.purchase_order_item_id)
    rows = db.session.execute(select(Receipt.id.label("receipt_id"), Receipt.number.label("receipt_number"), Receipt.supplier_id,
        Supplier.name.label("supplier_name"), ReceiptItem.line_number, ReceiptItem.description, ReceiptItem.unit, ReceiptItem.product_id,
        ReceiptItem.pending_quantity, PurchaseOrderItem.id.label("source_id"), PurchaseOrderItem.product_id.label("source_product_id"),
        PurchaseOrderItem.unit.label("source_unit"), PurchaseOrderItem.quantity.label("ordered_quantity"),
        func.coalesce(accepted.c.accepted_quantity, 0).label("used_quantity"), Product.is_active.label("product_active"),
        Product.unit.label("product_unit"), PurchaseOrder.status.label("order_status"), PurchaseOrder.confirmed_at,
        PurchaseOrder.number.label("order_number"), PurchaseOrder.supplier_id.label("source_supplier_id"), PurchaseOrder.owner_id)
        .select_from(ReceiptItem).join(Receipt, Receipt.id == ReceiptItem.receipt_id)
        .join(Supplier, Supplier.id == Receipt.supplier_id).outerjoin(PurchaseOrderItem, PurchaseOrderItem.id == source_id)
        .outerjoin(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .outerjoin(Product, Product.id == PurchaseOrderItem.product_id)
        .outerjoin(accepted, accepted.c.order_item_id == PurchaseOrderItem.id)
        .where(Receipt.status == "CONFIRMED", Receipt.confirmed_at.is_not(None), Receipt.confirmed_by_id.is_not(None),
               ReceiptItem.origin_item_id.is_(None), ReceiptItem.pending_quantity > 0)
        .order_by(Receipt.received_at, Receipt.id, ReceiptItem.line_number)).all()
    available = {}
    items = []
    for row in rows:
        compatible = (row.source_id is not None and row.order_status == "CONFIRMED" and row.confirmed_at is not None
            and row.source_supplier_id == row.supplier_id and row.source_unit == row.unit
            and (row.product_id is None or row.product_id == row.source_product_id)
            and row.product_active and row.product_unit == row.unit)
        ready = Decimal("0")
        if compatible:
            remaining = available.setdefault(row.source_id, max(row.ordered_quantity - row.used_quantity, Decimal("0")))
            ready = min(row.pending_quantity, remaining)
            available[row.source_id] -= ready
        common = {key: getattr(row, key) for key in ("receipt_number", "supplier_name", "line_number", "description", "unit", "order_number", "owner_id")}
        if ready:
            items.append({**common, "role": Role.DEPOZIT, "quantity": format(ready, ".3f")})
        if row.pending_quantity > ready:
            items.append({**common, "role": Role.ACHIZITII, "quantity": format(row.pending_quantity - ready, ".3f")})
    return items


def build_receipt_digests(role):
    today = bucharest_date()
    users = db.session.execute(select(User.id, User.name, User.email).where(User.is_active.is_(True), User.role == role).order_by(User.id)).all()
    by_id = {user.id: user for user in users}
    groups = {}
    skipped = 0
    for item in pending_responsibilities():
        if item["role"] != role:
            continue
        recipients = [by_id[item["owner_id"]]] if role == Role.ACHIZITII and item["owner_id"] in by_id else users
        if not recipients:
            skipped += 1
        for user in recipients:
            groups.setdefault(user.id, {"user": user, "items": []})["items"].append(item)
    messages = []
    for user_id, group in groups.items():
        user = group["user"]
        label = "clarificari receptii" if role == Role.ACHIZITII else "marfa in asteptarea acceptarii"
        messages.append({"recipient_user_id": user_id, "to": user.email,
            "subject": f"Ruris - {label} - {today.isoformat()}", "item_count": len(group["items"]),
            "body": render_template("emails/receipt_clarifications.txt", name=user.name, as_of=today.isoformat(),
                buyer=role == Role.ACHIZITII, items=group["items"]).strip()})
    return {"as_of": today.isoformat(), "timezone": "Europe/Bucharest", "messages": messages, "skipped_items": skipped}


def build_buyer_receipt_digests():
    return build_receipt_digests(Role.ACHIZITII)


def build_warehouse_receipt_digests():
    return build_receipt_digests(Role.DEPOZIT)
