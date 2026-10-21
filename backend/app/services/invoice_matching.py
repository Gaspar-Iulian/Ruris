from decimal import Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import InvoiceAllocation, InvoiceIssue, InvoiceItem, PurchaseOrder, PurchaseOrderItem, Receipt, ReceiptItem
from app.services.invoice_allocations import allocation_data
from app.services.invoice_issues import issue_data
from app.services.invoices import get_invoice


def get_matching(invoice_id):
    invoice = get_invoice(invoice_id)
    allocations = db.session.scalars(select(InvoiceAllocation).join(InvoiceItem, InvoiceItem.id == InvoiceAllocation.invoice_item_id)
        .where(InvoiceItem.invoice_id == invoice_id, InvoiceAllocation.status == "ACTIVE").order_by(InvoiceAllocation.id)).all()
    used = select(InvoiceAllocation.receipt_item_id.label("receipt_item_id"), func.sum(InvoiceAllocation.quantity).label("quantity"))\
        .where(InvoiceAllocation.status == "ACTIVE").group_by(InvoiceAllocation.receipt_item_id).subquery()
    products = {item["product_id"] for item in invoice["items"]}
    rows = db.session.execute(select(ReceiptItem, Receipt, PurchaseOrderItem, PurchaseOrder, func.coalesce(used.c.quantity, 0))
        .select_from(ReceiptItem)
        .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
        .join(PurchaseOrderItem, PurchaseOrderItem.id == ReceiptItem.purchase_order_item_id)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .outerjoin(used, used.c.receipt_item_id == ReceiptItem.id)
        .where(ReceiptItem.product_id.in_(products), Receipt.supplier_id == invoice["supplier_id"],
               PurchaseOrder.supplier_id == invoice["supplier_id"], Receipt.status == "CONFIRMED",
               Receipt.confirmed_at.is_not(None), Receipt.confirmed_by_id.is_not(None),
               PurchaseOrder.status.in_(("CONFIRMED", "CLOSED")), PurchaseOrder.confirmed_at.is_not(None),
               ReceiptItem.accepted_quantity > 0)
        .order_by(Receipt.received_at, ReceiptItem.id)).all() if products else []
    lines = []
    for line in invoice["items"]:
        allocated = sum((item.quantity for item in allocations if item.invoice_item_id == line["id"]), Decimal("0"))
        candidates = []
        for received, receipt, ordered, order, reserved in rows:
            if (received.product_id != line["product_id"] or ordered.product_id != line["product_id"]
                    or (line["purchase_order_item_id"] is not None and line["purchase_order_item_id"] != ordered.id)):
                continue
            differences = []
            for mismatch, code in [(line["unit"] != received.unit or line["unit"] != ordered.unit, "UNIT"),
                                   (invoice["currency"] != order.currency, "CURRENCY"),
                                   (Decimal(line["unit_price"]) != ordered.unit_price, "PRICE"),
                                   (Decimal(line["vat_rate"]) != ordered.vat_rate, "VAT")]:
                if mismatch:
                    differences.append(code)
            candidates.append({"receipt_item_id": received.id, "receipt_id": receipt.id, "receipt_number": receipt.number,
                "order_number": order.number, "order_item_id": ordered.id, "delivery_reference": receipt.delivery_reference,
                "accepted_quantity": format(received.accepted_quantity, ".3f"), "allocated_quantity": format(reserved, ".3f"),
                "available_quantity": format(max(received.accepted_quantity - reserved, Decimal("0")), ".3f"),
                "order_unit_price": format(ordered.unit_price, ".4f"), "order_vat_rate": format(ordered.vat_rate, ".2f"),
                "order_currency": order.currency, "eligible": not differences, "differences": differences})
        lines.append({**line, "allocated_quantity": format(allocated, ".3f"),
            "remaining_quantity": format(max(Decimal(line["quantity"]) - allocated, Decimal("0")), ".3f"), "candidates": candidates})
    issues = db.session.scalars(select(InvoiceIssue).where(InvoiceIssue.invoice_id == invoice_id,
        InvoiceIssue.resolved_at.is_(None)).order_by(InvoiceIssue.id)).all()
    receipt_names = {received.id: (receipt.number, order.number) for received, receipt, ordered, order, reserved in rows}
    active = [{**allocation_data(item), "receipt_number": receipt_names.get(item.receipt_item_id, (None, None))[0],
               "order_number": receipt_names.get(item.receipt_item_id, (None, None))[1]} for item in allocations]
    return {"invoice": invoice, "items": lines, "allocations": active,
            "issues": [issue_data(item) for item in issues]}
