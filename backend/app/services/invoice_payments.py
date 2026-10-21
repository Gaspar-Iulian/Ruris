from datetime import datetime, timezone
import re

from sqlalchemy import func, select

from app.extensions import db
from app.models import Invoice, InvoiceIssue, Role, User
from app.services.audit import record_audit
from app.services.invoices import InvoiceConflictError, InvoiceForbiddenError, InvoiceNotFoundError, invoice_data
from app.services.purchase_orders import positive_id


def record_payment(*, actor_user_id, invoice_id, version, reason, paid_at, payment_reference):
    try:
        positive_id(invoice_id)
        if type(version) is not int or not 1 <= version < 2147483647:
            raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv sub 2147483647.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        if (not isinstance(payment_reference, str) or not 1 <= len(payment_reference.strip()) <= 120
                or any(ord(char) < 32 or ord(char) == 127 for char in payment_reference)):
            raise ValueError("Referinta platii trebuie sa aiba 1-120 de caractere, fara caractere de control.")
        if not isinstance(paid_at, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", paid_at
        ):
            raise ValueError("Data platii trebuie sa fie ISO 8601, cu ora si fus orar explicit.")
        try:
            payment_time = datetime.fromisoformat(paid_at).astimezone(timezone.utc)
        except (ValueError, OverflowError) as error:
            raise ValueError("Data platii nu este valida.") from error
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.CONTABILITATE:
            raise InvoiceForbiddenError("Doar contabilitatea poate inregistra plati.")
        invoice = db.session.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update().execution_options(populate_existing=True))
        if invoice is None:
            raise InvoiceNotFoundError("Factura nu a fost gasita.")
        if invoice.status != "APPROVED" or invoice.version != version:
            raise InvoiceConflictError("Plata necesita o factura APPROVED cu versiunea curenta, fara plata deja inregistrata.")
        if invoice.approved_at is None or invoice.approved_by_id is None or invoice.total_ron is None:
            raise InvoiceConflictError("Factura nu are o aprobare completa.")
        if db.session.scalar(select(InvoiceIssue.id).where(InvoiceIssue.invoice_id == invoice.id, InvoiceIssue.resolved_at.is_(None)).limit(1)) is not None:
            raise InvoiceConflictError("Factura are blocaje deschise care necesita clarificare.")
        now = db.session.scalar(select(func.clock_timestamp()))
        if payment_time < invoice.approved_at or payment_time > now:
            raise ValueError("Data platii trebuie sa fie dupa aprobare si sa nu fie in viitor.")
        before = invoice_data(invoice, include_items=False)
        invoice.status = "PAID"
        invoice.paid_at = payment_time
        invoice.paid_by_id = actor.id
        invoice.payment_reference = payment_reference.strip()
        invoice.version += 1
        record_audit(action="PAY", entity_type="invoices", entity_id=invoice.id, actor_user_id=actor.id,
                     before={key: value for key, value in before.items() if key != "id"},
                     after={key: value for key, value in invoice_data(invoice, include_items=False).items() if key != "id"}, reason=reason.strip())
        result = invoice_data(invoice)
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise
