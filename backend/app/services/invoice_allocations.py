from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import Invoice, InvoiceAllocation, InvoiceItem, PurchaseOrder, PurchaseOrderItem, Receipt, ReceiptItem, Role, User
from app.services.audit import record_audit
from app.services.invoice_issues import invalidate_verification
from app.services.invoices import InvoiceConflictError, InvoiceForbiddenError, InvoiceNotFoundError, invoice_data
from app.services.purchase_orders import decimal_value, positive_id


def allocation_data(allocation):
    return {"id": allocation.id, "invoice_item_id": allocation.invoice_item_id,
            "receipt_item_id": allocation.receipt_item_id, "quantity": format(allocation.quantity, ".3f"),
            "status": allocation.status,
            "released_at": allocation.released_at.isoformat() if allocation.released_at else None}


def release_allocations(*, actor_user_id, invoice_id, version, reason, allocation_ids):
    try:
        positive_id(invoice_id)
        if type(version) is not int or not 1 <= version < 2147483647:
            raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv sub 2147483647.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        if not isinstance(allocation_ids, list) or not 1 <= len(allocation_ids) <= 100:
            raise ValueError("Trimite intre 1 si 100 de identificatori de alocari.")
        ids = [positive_id(value) for value in allocation_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("Identificatorii alocarilor nu se pot repeta.")
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.CONTABILITATE:
            raise InvoiceForbiddenError("Doar contabilitatea poate elibera alocari.")
        invoice = db.session.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update().execution_options(populate_existing=True))
        if invoice is None:
            raise InvoiceNotFoundError("Factura nu a fost gasita.")
        if invoice.status not in ("DRAFT", "BLOCKED", "VERIFIED") or invoice.version != version:
            raise InvoiceConflictError("Factura a fost modificata sau nu mai este o ciorna. Reincarca documentul.")
        query = select(InvoiceAllocation).join(InvoiceItem, InvoiceItem.id == InvoiceAllocation.invoice_item_id).where(
            InvoiceItem.invoice_id == invoice.id, InvoiceAllocation.id.in_(ids))
        allocations = db.session.scalars(query.order_by(InvoiceAllocation.id).execution_options(populate_existing=True)).all()
        if len(allocations) != len(ids):
            raise ValueError("Toate alocarile trebuie sa existe si sa apartina facturii curente.")
        receipt_ids = sorted({item.receipt_item_id for item in allocations})
        db.session.scalars(select(ReceiptItem).where(ReceiptItem.id.in_(receipt_ids)).order_by(ReceiptItem.id).with_for_update()).all()
        allocations = db.session.scalars(query.order_by(InvoiceAllocation.id).with_for_update(of=InvoiceAllocation)
                                        .execution_options(populate_existing=True)).all()
        if any(item.status != "ACTIVE" for item in allocations):
            raise InvoiceConflictError("O alocare selectata a fost deja eliberata. Reincarca documentul.")
        before = invoice_data(invoice, include_items=False)
        released_at = db.session.scalar(select(func.clock_timestamp()))
        for allocation in allocations:
            previous = allocation_data(allocation)
            allocation.status = "RELEASED"
            allocation.released_at = released_at
            record_audit(action="RELEASE", entity_type="invoice_allocations", entity_id=allocation.id, actor_user_id=actor.id,
                         before={key: value for key, value in previous.items() if key != "id"},
                         after={key: value for key, value in allocation_data(allocation).items() if key != "id"}, reason=reason.strip())
        invalidate_verification(invoice, actor_user_id=actor.id, reason=reason.strip())
        invoice.version += 1
        record_audit(action="UPDATE", entity_type="invoices", entity_id=invoice.id, actor_user_id=actor.id,
                     before={key: value for key, value in before.items() if key != "id"},
                     after={key: value for key, value in invoice_data(invoice, include_items=False).items() if key != "id"}, reason=reason.strip())
        result = {"invoice_id": invoice.id, "version": invoice.version, "allocations": [allocation_data(item) for item in allocations]}
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def allocated_quantities(column, ids):
    return dict(db.session.execute(select(column, func.sum(InvoiceAllocation.quantity))
                                   .where(column.in_(ids), InvoiceAllocation.status == "ACTIVE").group_by(column)).all())


def create_allocations(*, actor_user_id, invoice_id, version, reason, items):
    try:
        positive_id(invoice_id)
        if type(version) is not int or not 1 <= version < 2147483647:
            raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv sub 2147483647.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("Trimite intre 1 si 100 de alocari.")
        parsed = []
        pairs = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {"invoice_item_id", "receipt_item_id", "quantity"}:
                raise ValueError("Alocarea necesita invoice_item_id, receipt_item_id si quantity.")
            values = {"invoice_item_id": positive_id(item["invoice_item_id"]),
                      "receipt_item_id": positive_id(item["receipt_item_id"]),
                      "quantity": decimal_value(item["quantity"], scale=3, integer_digits=15, positive=True)}
            pair = (values["invoice_item_id"], values["receipt_item_id"])
            if pair in pairs:
                raise ValueError("Aceeasi pereche factura-receptie poate aparea o singura data in cerere.")
            pairs.add(pair)
            parsed.append(values)
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.CONTABILITATE:
            raise InvoiceForbiddenError("Doar contabilitatea poate aloca facturi.")
        invoice = db.session.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update().execution_options(populate_existing=True))
        if invoice is None:
            raise InvoiceNotFoundError("Factura nu a fost gasita.")
        if invoice.status not in ("DRAFT", "BLOCKED", "VERIFIED") or invoice.version != version:
            raise InvoiceConflictError("Factura a fost modificata sau nu mai este o ciorna. Reincarca documentul.")
        invoice_items = {item.id: item for item in invoice.items}
        if {item["invoice_item_id"] for item in parsed} - invoice_items.keys():
            raise ValueError("Toate pozitiile facturii trebuie sa apartina documentului curent.")
        receipt_ids = sorted({item["receipt_item_id"] for item in parsed})
        receipts = {item.id: item for item in db.session.scalars(select(ReceiptItem).where(ReceiptItem.id.in_(receipt_ids))
                    .order_by(ReceiptItem.id).with_for_update().execution_options(populate_existing=True)).all()}
        if len(receipts) != len(receipt_ids):
            raise ValueError("Una dintre pozitiile receptiei nu exista.")
        used_receipts = defaultdict(Decimal, allocated_quantities(InvoiceAllocation.receipt_item_id, receipt_ids))
        used_invoice = defaultdict(Decimal, allocated_quantities(InvoiceAllocation.invoice_item_id, invoice_items.keys()))
        for values in parsed:
            line = invoice_items[values["invoice_item_id"]]
            received = receipts[values["receipt_item_id"]]
            source = db.session.execute(select(Receipt, PurchaseOrderItem, PurchaseOrder)
                .select_from(Receipt).join(PurchaseOrderItem, PurchaseOrderItem.id == received.purchase_order_item_id)
                .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
                .where(Receipt.id == received.receipt_id)).first()
            if source is None:
                raise InvoiceConflictError("Receptia necesita o legatura valida la comanda.")
            receipt, ordered, order = source
            if (receipt.status != "CONFIRMED" or receipt.confirmed_at is None or receipt.confirmed_by_id is None
                    or order.status not in ("CONFIRMED", "CLOSED") or order.confirmed_at is None):
                raise InvoiceConflictError("Alocarea necesita receptie confirmata si comanda confirmata.")
            if (invoice.supplier_id != receipt.supplier_id or invoice.supplier_id != order.supplier_id
                    or (line.purchase_order_item_id is not None and line.purchase_order_item_id != ordered.id)
                    or line.product_id != received.product_id or line.product_id != ordered.product_id
                    or line.unit != received.unit or line.unit != ordered.unit
                    or invoice.currency != order.currency or line.unit_price != ordered.unit_price or line.vat_rate != ordered.vat_rate):
                raise InvoiceConflictError("Furnizorul, produsul, unitatea, moneda, pretul si TVA trebuie sa corespunda comenzii si receptiei.")
            used_receipts[received.id] += values["quantity"]
            used_invoice[line.id] += values["quantity"]
            if used_receipts[received.id] > received.accepted_quantity or used_invoice[line.id] > line.quantity:
                raise InvoiceConflictError("Cantitatea depaseste restul acceptat disponibil sau cantitatea facturata nealocata.")
        before = invoice_data(invoice, include_items=False)
        allocations = [InvoiceAllocation(**values) for values in parsed]
        db.session.add_all(allocations)
        invalidate_verification(invoice, actor_user_id=actor.id, reason=reason.strip())
        invoice.version += 1
        db.session.flush()
        for allocation in allocations:
            record_audit(action="CREATE", entity_type="invoice_allocations", entity_id=allocation.id, actor_user_id=actor.id,
                         after={key: value for key, value in allocation_data(allocation).items() if key != "id"}, reason=reason.strip())
        record_audit(action="UPDATE", entity_type="invoices", entity_id=invoice.id, actor_user_id=actor.id,
                     before={key: value for key, value in before.items() if key != "id"},
                     after={key: value for key, value in invoice_data(invoice, include_items=False).items() if key != "id"}, reason=reason.strip())
        result = {"invoice_id": invoice.id, "version": invoice.version, "allocations": [allocation_data(item) for item in allocations]}
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def list_allocations(invoice_id, *, page, per_page):
    positive_id(invoice_id)
    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        raise InvoiceNotFoundError("Factura nu a fost gasita.")
    query = select(InvoiceAllocation).join(InvoiceItem, InvoiceItem.id == InvoiceAllocation.invoice_item_id).where(InvoiceItem.invoice_id == invoice_id)
    rows = db.session.scalars(query.order_by(InvoiceAllocation.id).offset((page - 1) * per_page).limit(per_page)).all()
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    return {"invoice_id": invoice_id, "version": invoice.version, "allocations": [allocation_data(item) for item in rows],
            "total": total, "page": page, "per_page": per_page}
