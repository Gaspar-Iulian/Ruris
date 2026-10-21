from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
import re

from sqlalchemy import func, select

from app.extensions import db
from app.models import Invoice, InvoiceAllocation, InvoiceIssue, InvoiceItem, PurchaseOrder, PurchaseOrderItem, Role, User
from app.services.invoice_issues import invalidate_verification
from app.services.audit import record_audit
from app.services.purchase_orders import decimal_value, lock_catalog, positive_id


class InvoiceForbiddenError(PermissionError):
    pass


class InvoiceNotFoundError(LookupError):
    pass


class InvoiceConflictError(ValueError):
    pass


def update_invoice(*, actor_user_id, invoice_id, version, reason, **data):
    try:
        positive_id(invoice_id)
        positive_id(version)
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        fields, parsed = parse_invoice(**data, editing=True)
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.CONTABILITATE:
            raise InvoiceForbiddenError("Doar contabilitatea poate modifica facturi.")
        invoice = db.session.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update().execution_options(populate_existing=True))
        if invoice is None:
            raise InvoiceNotFoundError("Factura nu a fost gasita.")
        if invoice.status not in ("DRAFT", "BLOCKED", "VERIFIED") or invoice.version != version:
            raise InvoiceConflictError("Factura nu mai este o ciorna sau a fost modificata. Reincarca documentul.")
        if db.session.scalar(select(InvoiceAllocation.id).join(InvoiceItem, InvoiceItem.id == InvoiceAllocation.invoice_item_id)
                             .where(InvoiceItem.invoice_id == invoice.id, InvoiceAllocation.status == "ACTIVE").limit(1)) is not None:
            raise InvoiceConflictError("Factura are alocari active. Elibereaza-le inainte de corectare.")
        products = lock_catalog(fields["supplier_id"], parsed)
        existing = {item.id: item for item in invoice.items}
        validate_order_sources(parsed, fields["supplier_id"], products, existing)
        ids = [item["id"] for item in parsed if "id" in item]
        if len(ids) != len(set(ids)) or set(ids) - existing.keys():
            raise ValueError("Pozitiile existente trebuie sa apartina facturii si sa nu se repete.")
        removed_ids = existing.keys() - set(ids)
        if removed_ids and db.session.scalar(select(InvoiceAllocation.id).where(
                InvoiceAllocation.invoice_item_id.in_(removed_ids)).limit(1)) is not None:
            raise InvoiceConflictError("O pozitie cu istoric de alocari trebuie pastrata. Poti corecta valorile ei dupa eliberare.")
        if removed_ids and db.session.scalar(select(InvoiceIssue.id).where(InvoiceIssue.invoice_item_id.in_(removed_ids)).limit(1)) is not None:
            raise InvoiceConflictError("O pozitie cu istoric de verificare trebuie pastrata; corecteaza valorile ei.")
        for item in parsed:
            if "id" in item and existing[item["id"]].product_id != item["product_id"]:
                raise ValueError("Produsul unei pozitii existente nu poate fi schimbat; adauga o pozitie noua.")
        before = invoice_data(invoice)
        old_lines = {item.id: item_data(item) for item in invoice.items}
        unchanged = all(getattr(invoice, key) == value for key, value in fields.items())
        unchanged = unchanged and len(parsed) == len(invoice.items) and all(
            values.get("id") == item.id and all(getattr(item, key) == value for key, value in values.items())
            for item, values in zip(invoice.items, parsed)
        )
        if unchanged:
            db.session.commit()
            return before
        invalidate_verification(invoice, actor_user_id=actor.id, reason=reason.strip())
        for item in invoice.items:
            item.line_number += 100
        db.session.flush()
        for key, value in fields.items():
            setattr(invoice, key, value)
        retained = []
        for line, values in enumerate(parsed, 1):
            values = dict(values)
            item_id = values.pop("id", None)
            if item_id is None:
                product = products[values["product_id"]]
                item = InvoiceItem(description=product.name, unit=product.unit, **values)
                invoice.items.append(item)
            else:
                item = existing[item_id]
                for key, value in values.items():
                    setattr(item, key, value)
            item.line_number = line
            retained.append(item)
        for item_id, item in existing.items():
            if item_id not in ids:
                invoice.items.remove(item)
                db.session.delete(item)
        db.session.flush()
        invoice.items.sort(key=lambda item: item.line_number)
        after = invoice_data(invoice)
        if before != after:
            after["status"] = invoice.status
            for key in ("exchange_rate_id", "exchange_rate_value", "exchange_rate_date", "exchange_rate_source", "total_ron"):
                after[key] = None
            invoice.version += 1
            after["version"] = invoice.version
            record_audit(action="UPDATE", entity_type="invoices", entity_id=invoice.id, actor_user_id=actor.id,
                         before={key: value for key, value in before.items() if key not in {"id", "items"}},
                         after={key: value for key, value in after.items() if key not in {"id", "items"}}, reason=reason.strip())
            for item in retained:
                snapshot = item_data(item)
                previous = old_lines.get(item.id)
                if snapshot != previous:
                    record_audit(action="UPDATE" if previous else "CREATE", entity_type="invoice_items", entity_id=item.id,
                                 actor_user_id=actor.id, before={"invoice_id": invoice.id, **{key: value for key, value in previous.items() if key != "id"}} if previous else None,
                                 after={"invoice_id": invoice.id, **{key: value for key, value in snapshot.items() if key != "id"}}, reason=reason.strip())
            for item_id in existing.keys() - set(ids):
                record_audit(action="DELETE", entity_type="invoice_items", entity_id=item_id, actor_user_id=actor.id,
                             before={"invoice_id": invoice.id, **{key: value for key, value in old_lines[item_id].items() if key != "id"}}, reason=reason.strip())
        db.session.commit()
        return after
    except Exception:
        db.session.rollback()
        raise


def reference(value, maximum, *, optional=False):
    if not isinstance(value, str):
        raise ValueError("Seria si numarul trebuie sa fie texte.")
    value = value.strip().upper()
    if len(value) > maximum or (not value and not optional) or (value and not re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]*", value)):
        raise ValueError("Referinta permite litere A-Z, cifre, punct, cratima, / si _; fara spatii interne.")
    return value


def document_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Data trebuie sa fie YYYY-MM-DD.")
    return date.fromisoformat(value)


def money(value):
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if value >= Decimal("10000000000000000"):
        raise ValueError("Suma depaseste limita permisa.")
    return value


def item_data(item):
    result = {key: getattr(item, key) for key in ("id", "line_number", "product_id", "description", "unit")}
    result["purchase_order_item_id"] = item.purchase_order_item_id
    for key, scale in (("quantity", 3), ("unit_price", 4), ("vat_rate", 2), ("net_amount", 2), ("vat_amount", 2), ("total_amount", 2)):
        result[key] = format(getattr(item, key), f".{scale}f")
    return result


def invoice_data(invoice, *, include_items=True):
    result = {key: getattr(invoice, key) for key in ("id", "supplier_id", "series", "number", "currency", "status", "created_by_id", "version")}
    for key in ("invoice_date", "due_date"):
        result[key] = getattr(invoice, key).isoformat()
    for key in ("net_amount", "vat_amount", "total_amount"):
        result[key] = format(getattr(invoice, key), ".2f")
    result["exchange_rate_id"] = invoice.exchange_rate_id
    result["approved_by_id"] = invoice.approved_by_id
    result["approved_at"] = invoice.approved_at.isoformat() if invoice.approved_at else None
    result["paid_by_id"] = invoice.paid_by_id
    result["paid_at"] = invoice.paid_at.isoformat() if invoice.paid_at else None
    result["payment_reference"] = invoice.payment_reference
    result["exchange_rate_source"] = invoice.exchange_rate_source
    result["exchange_rate_date"] = invoice.exchange_rate_date.isoformat() if invoice.exchange_rate_date else None
    result["exchange_rate_value"] = format(invoice.exchange_rate_value, ".6f") if invoice.exchange_rate_value is not None else None
    result["total_ron"] = format(invoice.total_ron, ".2f") if invoice.total_ron is not None else None
    if include_items:
        result["items"] = [item_data(item) for item in invoice.items]
    return result


def parse_invoice(supplier_id, series, number, invoice_date, due_date, currency, items, *, editing=False):
    positive_id(supplier_id)
    series, number = reference(series, 40, optional=True), reference(number, 80)
    invoice_date, due_date = document_date(invoice_date), document_date(due_date)
    if due_date < invoice_date:
        raise ValueError("Scadenta nu poate preceda data facturii.")
    if not isinstance(currency, str) or currency not in ("RON", "EUR"):
        raise ValueError("Moneda trebuie sa fie RON sau EUR.")
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("Trimite o lista cu cel mult 100 de pozitii.")
    parsed = []
    with localcontext() as context:
        context.prec = 50
        for item in items:
            if not isinstance(item, dict) or set(item) - ({"id", "purchase_order_item_id"} if editing else {"purchase_order_item_id"}) != {"product_id", "quantity", "unit_price", "vat_rate"}:
                raise ValueError("Pozitia necesita product_id, quantity, unit_price si vat_rate.")
            values = {"product_id": positive_id(item["product_id"]),
                      "quantity": decimal_value(item["quantity"], scale=3, integer_digits=15, positive=True),
                      "unit_price": decimal_value(item["unit_price"], scale=4, integer_digits=14),
                      "vat_rate": decimal_value(item["vat_rate"], scale=2, integer_digits=3, maximum=100)}
            values["net_amount"] = money(values["quantity"] * values["unit_price"])
            values["vat_amount"] = money(values["net_amount"] * values["vat_rate"] / 100)
            values["total_amount"] = money(values["net_amount"] + values["vat_amount"])
            if "id" in item:
                values["id"] = positive_id(item["id"])
            if "purchase_order_item_id" in item:
                values["purchase_order_item_id"] = positive_id(item["purchase_order_item_id"]) if item["purchase_order_item_id"] is not None else None
            parsed.append(values)
        totals = {key: money(sum((item[key] for item in parsed), Decimal("0")))
                  for key in ("net_amount", "vat_amount", "total_amount")}
    return {"supplier_id": supplier_id, "series": series, "number": number, "invoice_date": invoice_date,
            "due_date": due_date, "currency": currency, **totals}, parsed


def validate_order_sources(items, supplier_id, products, existing=None):
    existing = existing or {}
    for item in items:
        if "purchase_order_item_id" not in item and item.get("id") in existing:
            item["purchase_order_item_id"] = existing[item["id"]].purchase_order_item_id
    ids = {item["purchase_order_item_id"] for item in items if item.get("purchase_order_item_id") is not None}
    rows = db.session.execute(select(PurchaseOrderItem, PurchaseOrder).join(PurchaseOrder,
        PurchaseOrder.id == PurchaseOrderItem.purchase_order_id).where(PurchaseOrderItem.id.in_(ids))).all() if ids else []
    sources = {line.id: (line, order) for line, order in rows}
    for item in items:
        source_id = item.get("purchase_order_item_id")
        if source_id is None:
            continue
        source = sources.get(source_id)
        if source is None:
            raise ValueError("Pozitia de comanda nu exista.")
        line, order = source
        if (order.status not in ("CONFIRMED", "CLOSED") or order.confirmed_at is None
                or order.supplier_id != supplier_id or line.product_id != item["product_id"]
                or line.unit != products[item["product_id"]].unit):
            raise ValueError("Pozitia facturii necesita o comanda confirmata, cu acelasi furnizor, produs si unitate.")


def create_invoice(*, actor_user_id, supplier_id, series, number, invoice_date, due_date, currency, items):
    try:
        fields, parsed = parse_invoice(supplier_id, series, number, invoice_date, due_date, currency, items)
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.CONTABILITATE:
            raise InvoiceForbiddenError("Doar contabilitatea poate inregistra facturi.")
        products = lock_catalog(supplier_id, parsed)
        validate_order_sources(parsed, supplier_id, products)
        invoice = Invoice(created_by_id=actor.id, **fields)
        for line, values in enumerate(parsed, 1):
            product = products[values["product_id"]]
            invoice.items.append(InvoiceItem(line_number=line, description=product.name, unit=product.unit, **values))
        db.session.add(invoice)
        db.session.flush()
        result = invoice_data(invoice)
        record_audit(action="CREATE", entity_type="invoices", entity_id=invoice.id, actor_user_id=actor.id,
                     after={key: value for key, value in result.items() if key not in {"id", "items"}})
        for item in invoice.items:
            record_audit(action="CREATE", entity_type="invoice_items", entity_id=item.id, actor_user_id=actor.id,
                         after={"invoice_id": invoice.id, **{key: value for key, value in item_data(item).items() if key != "id"}})
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def list_invoices(*, page, per_page):
    invoices = db.session.scalars(select(Invoice).order_by(Invoice.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    return {"invoices": [invoice_data(invoice, include_items=False) for invoice in invoices],
            "total": db.session.scalar(select(func.count()).select_from(Invoice)), "page": page, "per_page": per_page}


def get_invoice(invoice_id):
    positive_id(invoice_id)
    invoice = db.session.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if invoice is None:
        raise InvoiceNotFoundError("Factura nu a fost gasita.")
    return invoice_data(invoice)
