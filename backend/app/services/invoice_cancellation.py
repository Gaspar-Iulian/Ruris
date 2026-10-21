from sqlalchemy import func, select

from app.extensions import db
from app.models import Invoice, InvoiceAllocation, InvoiceItem, ReceiptItem, Role, User
from app.services.audit import record_audit
from app.services.invoice_allocations import allocation_data
from app.services.invoice_issues import invalidate_verification
from app.services.invoices import InvoiceConflictError, InvoiceForbiddenError, InvoiceNotFoundError, invoice_data
from app.services.purchase_orders import positive_id


def cancel_invoice(*, actor_user_id, invoice_id, version, reason):
    try:
        positive_id(invoice_id)
        if type(version) is not int or not 1 <= version < 2147483647:
            raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv sub 2147483647.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul anularii trebuie sa aiba intre 1 si 1000 de caractere.")
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.CONTABILITATE:
            raise InvoiceForbiddenError("Doar contabilitatea poate anula facturi.")
        invoice = db.session.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update().execution_options(populate_existing=True))
        if invoice is None:
            raise InvoiceNotFoundError("Factura nu a fost gasita.")
        if invoice.status not in ("DRAFT", "BLOCKED", "VERIFIED") or invoice.version != version:
            raise InvoiceConflictError("Doar o factura neaprobata, cu versiunea curenta, poate fi anulata. Reincarca documentul.")
        before = invoice_data(invoice, include_items=False)
        active = (select(InvoiceAllocation).join(InvoiceItem, InvoiceItem.id == InvoiceAllocation.invoice_item_id)
            .where(InvoiceItem.invoice_id == invoice.id, InvoiceAllocation.status == "ACTIVE"))
        allocations = db.session.scalars(active.order_by(InvoiceAllocation.id)).all()
        # Use the same lock order as allocation and release.
        db.session.scalars(select(ReceiptItem).where(ReceiptItem.id.in_({item.receipt_item_id for item in allocations}))
            .order_by(ReceiptItem.id).with_for_update()).all()
        allocations = db.session.scalars(active.order_by(InvoiceAllocation.id).with_for_update(of=InvoiceAllocation)
            .execution_options(populate_existing=True)).all()
        now = db.session.scalar(select(func.clock_timestamp()))
        for allocation in allocations:
            previous = allocation_data(allocation)
            allocation.status, allocation.released_at = "RELEASED", now
            record_audit(action="RELEASE", entity_type="invoice_allocations", entity_id=allocation.id, actor_user_id=actor.id,
                before={key: value for key, value in previous.items() if key != "id"},
                after={key: value for key, value in allocation_data(allocation).items() if key != "id"}, reason=reason.strip())
        invalidate_verification(invoice, actor_user_id=actor.id, reason=reason.strip())
        invoice.status, invoice.cancelled_by_id, invoice.cancelled_at = "CANCELLED", actor.id, now
        invoice.cancellation_reason = reason.strip()
        invoice.version += 1
        result = invoice_data(invoice)
        record_audit(action="CANCEL", entity_type="invoices", entity_id=invoice.id, actor_user_id=actor.id,
            before={key: value for key, value in before.items() if key != "id"},
            after={key: value for key, value in invoice_data(invoice, include_items=False).items() if key != "id"}, reason=reason.strip())
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise
