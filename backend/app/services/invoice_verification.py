from collections import defaultdict
from decimal import Decimal, localcontext

from sqlalchemy import func, select

from app.extensions import db
from app.models import Invoice, InvoiceAllocation, InvoiceIssue, InvoiceItem, PurchaseOrder, PurchaseOrderItem, Receipt, ReceiptItem, Role, User
from app.services.audit import record_audit
from app.services.exchange_rates import ExchangeRateUnavailable, get_eur_rate
from app.services.invoice_issues import audit_issue, issue_data
from app.services.invoices import InvoiceConflictError, InvoiceForbiddenError, InvoiceNotFoundError, invoice_data, money
from app.services.purchase_orders import positive_id


def verify_invoice(*, actor_user_id, invoice_id, version):
    return _review_invoice(actor_user_id=actor_user_id, invoice_id=invoice_id, version=version)


def approve_invoice(*, actor_user_id, invoice_id, version, reason):
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
        raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
    return _review_invoice(actor_user_id=actor_user_id, invoice_id=invoice_id, version=version, approve=True, reason=reason.strip())


def _review_invoice(*, actor_user_id, invoice_id, version, approve=False, reason=None):
    try:
        positive_id(invoice_id)
        if type(version) is not int or not 1 <= version < 2147483647:
            raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv sub 2147483647.")
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.CONTABILITATE:
            raise InvoiceForbiddenError("Doar contabilitatea poate verifica facturi.")
        invoice = db.session.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update().execution_options(populate_existing=True))
        if invoice is None:
            raise InvoiceNotFoundError("Factura nu a fost gasita.")
        if invoice.status not in ("DRAFT", "BLOCKED", "VERIFIED") or invoice.version != version:
            raise InvoiceConflictError("Factura a fost modificata sau starea nu permite verificarea. Reincarca documentul.")
        if approve and invoice.status != "VERIFIED":
            raise InvoiceConflictError("Doar o factura VERIFIED poate fi aprobata. Verifica factura mai intai.")
        before = invoice_data(invoice, include_items=False)
        found = {}

        def add(code, details, line_id=None, role="CONTABILITATE"):
            found[(line_id, code)] = (details, role)

        if not invoice.items:
            add("NO_ITEMS", "Factura nu contine pozitii.")
        allocations = db.session.scalars(select(InvoiceAllocation).join(InvoiceItem, InvoiceItem.id == InvoiceAllocation.invoice_item_id)
            .where(InvoiceItem.invoice_id == invoice.id, InvoiceAllocation.status == "ACTIVE").order_by(InvoiceAllocation.id)).all()
        receipt_ids = sorted({item.receipt_item_id for item in allocations})
        receipts = {item.id: item for item in db.session.scalars(select(ReceiptItem).where(ReceiptItem.id.in_(receipt_ids))
                    .order_by(ReceiptItem.id).with_for_update().execution_options(populate_existing=True)).all()}
        used = dict(db.session.execute(select(InvoiceAllocation.receipt_item_id, func.sum(InvoiceAllocation.quantity))
                    .where(InvoiceAllocation.receipt_item_id.in_(receipt_ids), InvoiceAllocation.status == "ACTIVE")
                    .group_by(InvoiceAllocation.receipt_item_id)).all())
        by_line = defaultdict(list)
        for allocation in allocations:
            by_line[allocation.invoice_item_id].append(allocation)
        with localcontext() as context:
            context.prec = 50
            for line in invoice.items:
                allocated = sum((item.quantity for item in by_line[line.id]), Decimal("0"))
                if allocated != line.quantity:
                    add("QUANTITY_NOT_COVERED", f"Cantitate facturata {line.quantity:.3f}; alocata {allocated:.3f}.", line.id)
                net = money(line.quantity * line.unit_price)
                vat = money(net * line.vat_rate / 100)
                if (net, vat, net + vat) != (line.net_amount, line.vat_amount, line.total_amount):
                    add("LINE_TOTAL_MISMATCH", "Sumele pozitiei nu corespund regulii de calcul si rotunjire.", line.id)
                for allocation in by_line[line.id]:
                    received = receipts.get(allocation.receipt_item_id)
                    source = None if received is None else db.session.execute(select(Receipt, PurchaseOrderItem, PurchaseOrder)
                        .select_from(Receipt).join(PurchaseOrderItem, PurchaseOrderItem.id == received.purchase_order_item_id)
                        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
                        .where(Receipt.id == received.receipt_id).execution_options(populate_existing=True)).first()
                    if source is None:
                        add("SOURCE_MISSING", "Alocarea nu are receptie si comanda identificabile.", line.id)
                        continue
                    receipt, ordered, order = source
                    if receipt.status != "CONFIRMED" or receipt.confirmed_at is None or receipt.confirmed_by_id is None:
                        add("RECEIPT_NOT_CONFIRMED", "Receptia sursa nu este confirmata complet.", line.id, "DEPOZIT")
                    if order.status not in ("CONFIRMED", "CLOSED") or order.confirmed_at is None:
                        add("ORDER_NOT_CONFIRMED", "Comanda sursa nu este confirmata.", line.id, "ACHIZITII")
                    if used.get(received.id, Decimal("0")) > received.accepted_quantity:
                        add("RECEIPT_OVERALLOCATED", "Alocarile active depasesc cantitatea acceptata a receptiei.", line.id, "DEPOZIT")
                    if (invoice.supplier_id != receipt.supplier_id or invoice.supplier_id != order.supplier_id
                            or (line.purchase_order_item_id is not None and line.purchase_order_item_id != ordered.id)
                            or line.product_id != received.product_id or line.product_id != ordered.product_id
                            or line.unit != received.unit or line.unit != ordered.unit):
                        add("IDENTITY_MISMATCH", "Furnizorul, produsul sau unitatea difera intre documente.", line.id)
                    if invoice.currency != order.currency or line.unit_price != ordered.unit_price or line.vat_rate != ordered.vat_rate:
                        add("TERMS_MISMATCH", "Moneda, pretul sau TVA difera fata de comanda.", line.id, "ACHIZITII")
            totals = tuple(sum((getattr(item, key) for item in invoice.items), Decimal("0")) for key in ("net_amount", "vat_amount", "total_amount"))
            if totals != (invoice.net_amount, invoice.vat_amount, invoice.total_amount):
                add("INVOICE_TOTAL_MISMATCH", "Sumele antetului difera fata de totalul pozitiilor.")
        for key in ("exchange_rate_id", "exchange_rate_value", "exchange_rate_date", "exchange_rate_source", "total_ron"):
            setattr(invoice, key, None)
        try:
            rate = get_eur_rate(invoice.invoice_date) if invoice.currency == "EUR" else None
            value = rate.rate if rate is not None else Decimal("1.000000")
            with localcontext() as context:
                context.prec = 50
                total_ron = money(invoice.total_amount * value)
            invoice.exchange_rate_id = rate.id if rate else None
            invoice.exchange_rate_value = value
            invoice.exchange_rate_date = invoice.invoice_date
            invoice.exchange_rate_source = "BNR" if rate else "IDENTITY"
            invoice.total_ron = total_ron
        except ExchangeRateUnavailable as error:
            add("EXCHANGE_RATE_MISSING", str(error))
        except ValueError:
            add("FX_CONVERSION_OVERFLOW", "Suma convertita depaseste limita monetara permisa.")
        now = db.session.scalar(select(func.clock_timestamp()))
        opened = db.session.scalars(select(InvoiceIssue).where(InvoiceIssue.invoice_id == invoice.id, InvoiceIssue.resolved_at.is_(None))).all()
        for issue in opened:
            if (issue.invoice_item_id, issue.code) not in found:
                previous = {key: value for key, value in issue_data(issue).items() if key != "id"}
                issue.resolved_at, issue.resolution = now, "RESOLVED"
                audit_issue(issue, actor_user_id=actor.id, action="RESOLVE", before=previous)
        existing = {(issue.invoice_item_id, issue.code): issue for issue in opened}
        for key, (details, role) in found.items():
            issue = existing.get(key)
            if issue is None:
                issue = InvoiceIssue(invoice_id=invoice.id, invoice_item_id=key[0], code=key[1], details=details,
                                     responsible_role=role, opened_at=now)
                db.session.add(issue)
                db.session.flush()
                audit_issue(issue, actor_user_id=actor.id, action="OPEN")
            elif issue.details != details or issue.responsible_role != role:
                previous = {key: value for key, value in issue_data(issue).items() if key != "id"}
                issue.details, issue.responsible_role = details, role
                audit_issue(issue, actor_user_id=actor.id, action="UPDATE", before=previous)
        invoice.status = "BLOCKED" if found else "VERIFIED"
        if approve and not found:
            invoice.status = "APPROVED"
            invoice.approved_by_id = actor.id
            invoice.approved_at = now
        invoice.version += 1
        record_audit(action="APPROVE" if approve and not found else "VERIFY", entity_type="invoices", entity_id=invoice.id, actor_user_id=actor.id,
                     before={key: value for key, value in before.items() if key != "id"},
                     after={key: value for key, value in invoice_data(invoice, include_items=False).items() if key != "id"}, reason=reason)
        db.session.flush()
        issues = db.session.scalars(select(InvoiceIssue).where(InvoiceIssue.invoice_id == invoice.id, InvoiceIssue.resolved_at.is_(None)).order_by(InvoiceIssue.id)).all()
        result = {"invoice": invoice_data(invoice), "issues": [issue_data(issue) for issue in issues]}
        if approve:
            result["approved"] = not bool(found)
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def list_issues(invoice_id, *, page, per_page):
    positive_id(invoice_id)
    if db.session.get(Invoice, invoice_id) is None:
        raise InvoiceNotFoundError("Factura nu a fost gasita.")
    query = select(InvoiceIssue).where(InvoiceIssue.invoice_id == invoice_id)
    rows = db.session.scalars(query.order_by(InvoiceIssue.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    return {"issues": [issue_data(issue) for issue in rows], "page": page, "per_page": per_page,
            "total": db.session.scalar(select(func.count()).select_from(query.subquery()))}
