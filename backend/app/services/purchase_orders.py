from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re

from sqlalchemy import Date, case, func, select

from app.extensions import db
from app.models import Product, PurchaseOrder, PurchaseOrderItem, Role, Supplier, User
from app.models import Invoice, InvoiceAllocation, InvoiceItem, Receipt, ReceiptItem
from app.services.audit import record_audit


class OrderCreationForbiddenError(PermissionError):
    pass


class OrderNotFoundError(LookupError):
    pass


class OrderManagementForbiddenError(PermissionError):
    pass


class OrderConflictError(ValueError):
    pass


def positive_id(value):
    if type(value) is not int or not 1 <= value <= 9223372036854775807:
        raise ValueError("Identificatorul trebuie sa fie un numar intreg pozitiv.")
    return value


def decimal_value(value, *, scale, integer_digits, positive=False, maximum=None):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) or len(value) > 40:
        raise ValueError("Cantitatile, preturile si TVA trebuie trimise ca texte zecimale, fara virgula sau exponent.")
    try:
        number = Decimal(value)
        if (number.as_tuple().exponent < -scale or number >= Decimal(10) ** integer_digits
                or positive and number <= 0 or maximum is not None and number > maximum):
            raise ValueError("Valoarea zecimala depaseste limitele sau precizia permisa.")
        return number.quantize(Decimal(1).scaleb(-scale))
    except InvalidOperation as error:
        raise ValueError("Valoare zecimala invalida.") from error


def order_data(order, *, include_items=True):
    data = {key: getattr(order, key) for key in (
        "id", "number", "supplier_id", "currency", "status", "owner_id", "created_by_id", "version",
    )}
    data["confirmed_at"] = order.confirmed_at.astimezone(timezone.utc).isoformat() if order.confirmed_at else None
    if include_items:
        data["items"] = [item_data(item) for item in order.items]
    return data


def item_data(item):
    return {"id": item.id, "line_number": item.line_number, "product_id": item.product_id,
            "description": item.description, "unit": item.unit, "quantity": format(item.quantity, ".3f"),
            "unit_price": format(item.unit_price, ".4f"), "vat_rate": format(item.vat_rate, ".2f"),
            "expected_date": item.expected_date.isoformat()}


def parse_order(supplier_id, currency, items, *, editing=False):
    positive_id(supplier_id)
    if not isinstance(currency, str) or currency not in ("RON", "EUR"):
        raise ValueError("Moneda trebuie sa fie RON sau EUR.")
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("Comanda trebuie sa contina o lista cu cel mult 100 de pozitii.")
    parsed = []
    fields = {"product_id", "quantity", "unit_price", "vat_rate", "expected_date"}
    for item in items:
        if not isinstance(item, dict) or not fields <= item.keys() or item.keys() - fields - ({"id"} if editing else set()):
            raise ValueError("Fiecare pozitie necesita product_id, quantity, unit_price, vat_rate si expected_date.")
        product_id = positive_id(item["product_id"])
        value = item["expected_date"]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Termenul trebuie sa fie o data valida YYYY-MM-DD.")
        try:
            expected = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError("Termenul trebuie sa fie o data valida YYYY-MM-DD.") from error
        parsed.append({"product_id": product_id, "expected_date": expected,
                       "quantity": decimal_value(item["quantity"], scale=3, integer_digits=15, positive=True),
                       "unit_price": decimal_value(item["unit_price"], scale=4, integer_digits=14),
                       "vat_rate": decimal_value(item["vat_rate"], scale=2, integer_digits=3, maximum=100)})
        if "id" in item:
            parsed[-1]["id"] = positive_id(item["id"])
    return parsed


def lock_catalog(supplier_id, parsed):
    supplier = db.session.scalar(select(Supplier).where(Supplier.id == supplier_id).with_for_update().execution_options(populate_existing=True))
    if supplier is None or not supplier.is_active:
        raise ValueError("Furnizorul trebuie sa existe si sa fie activ.")
    product_ids = sorted({item["product_id"] for item in parsed})
    products = db.session.scalars(select(Product).where(Product.id.in_(product_ids)).order_by(Product.id)
                                  .with_for_update().execution_options(populate_existing=True)).all()
    by_id = {product.id: product for product in products}
    if len(by_id) != len(product_ids) or any(not product.is_active for product in products):
        raise ValueError("Toate produsele trebuie sa existe si sa fie active.")
    return by_id


def create_order(*, actor_user_id, supplier_id, currency, items):
    try:
        parsed = parse_order(supplier_id, currency, items)
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.ACHIZITII:
            raise OrderCreationForbiddenError("Doar achizitiile pot crea comenzi.")
        by_id = lock_catalog(supplier_id, parsed)
        order = PurchaseOrder(supplier_id=supplier_id, currency=currency, owner_id=actor.id, created_by_id=actor.id)
        for line, item in enumerate(parsed, 1):
            product = by_id[item["product_id"]]
            order.items.append(PurchaseOrderItem(line_number=line, description=product.name, unit=product.unit, **item))
        db.session.add(order)
        db.session.flush()
        result = order_data(order)
        record_audit(action="CREATE", entity_type="purchase_orders", entity_id=order.id,
                     actor_user_id=actor.id, after={key: value for key, value in result.items() if key not in {"id", "items"}})
        for item in order.items:
            record_audit(action="CREATE", entity_type="purchase_order_items", entity_id=item.id, actor_user_id=actor.id,
                         after={"purchase_order_id": order.id, **{key: value for key, value in item_data(item).items() if key != "id"}})
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def edit_order(*, actor_user_id, order_id, version, reason, supplier_id, currency, items):
    try:
        if type(version) is not int or not 1 <= version <= 2147483647:
            raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        parsed = parse_order(supplier_id, currency, items, editing=True)
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.ACHIZITII:
            raise OrderManagementForbiddenError("Doar achizitiile pot modifica ciorne.")
        order = db.session.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id)
                                  .with_for_update().execution_options(populate_existing=True))
        if order is None:
            raise OrderNotFoundError("Comanda nu a fost gasita.")
        if order.status != "DRAFT":
            raise OrderConflictError("Doar ciornele pot fi modificate.")
        if order.version != version or version == 2147483647:
            raise OrderConflictError("Comanda a fost modificata. Reincarca datele inainte de salvare.")
        old = {item.id: item for item in order.items}
        existing_ids = [item["id"] for item in parsed if "id" in item]
        if len(existing_ids) != len(set(existing_ids)) or set(existing_ids) - old.keys():
            raise ValueError("Pozitiile existente trebuie sa apartina comenzii si sa apara o singura data.")
        if any(item["product_id"] != old[item["id"]].product_id for item in parsed if "id" in item):
            raise ValueError("Pentru alt produs elimina pozitia veche si adauga una noua, fara id.")
        by_id = lock_catalog(supplier_id, parsed)
        before = order_data(order)
        before_items = {item["id"]: item for item in before["items"]}
        desired = []
        for line, values in enumerate(parsed, 1):
            product = by_id[values["product_id"]]
            previous = old.get(values.get("id"))
            candidate = PurchaseOrderItem(line_number=line, description=previous.description if previous else product.name,
                                          unit=previous.unit if previous else product.unit,
                                          **{key: value for key, value in values.items() if key != "id"})
            desired.append((previous, candidate))
        unchanged = (order.supplier_id == supplier_id and order.currency == currency and len(desired) == len(old)
                     and all(previous is not None and item_data(candidate) == {**before_items[previous.id], "id": None}
                             for previous, candidate in desired))
        if unchanged:
            db.session.commit()
            return before
        removed = [item for item_id, item in old.items() if item_id not in existing_ids]
        for item in removed:
            order.items.remove(item)
            db.session.delete(item)
        # Move existing line numbers aside before reordering.
        for item in order.items:
            item.line_number += 100
        db.session.flush()
        for previous, candidate in desired:
            if previous is None:
                order.items.append(candidate)
            else:
                for field in ("line_number", "quantity", "unit_price", "vat_rate", "expected_date"):
                    setattr(previous, field, getattr(candidate, field))
        order.items.sort(key=lambda item: item.line_number)
        order.supplier_id = supplier_id
        order.currency = currency
        order.version += 1
        db.session.flush()
        result = order_data(order)
        record_audit(action="UPDATE", entity_type="purchase_orders", entity_id=order.id, actor_user_id=actor.id,
                     before={key: value for key, value in before.items() if key not in {"id", "items"}},
                     after={key: value for key, value in result.items() if key not in {"id", "items"}}, reason=reason.strip())
        for item in removed:
            record_audit(action="DELETE", entity_type="purchase_order_items", entity_id=item.id, actor_user_id=actor.id,
                         before={"purchase_order_id": order.id, **{key: value for key, value in before_items[item.id].items() if key != "id"}}, reason=reason.strip())
        for item in result["items"]:
            previous = before_items.get(item["id"])
            if previous == item:
                continue
            record_audit(action="UPDATE" if previous else "CREATE", entity_type="purchase_order_items", entity_id=item["id"], actor_user_id=actor.id,
                         before={"purchase_order_id": order.id, **{key: value for key, value in previous.items() if key != "id"}} if previous else None,
                         after={"purchase_order_id": order.id, **{key: value for key, value in item.items() if key != "id"}}, reason=reason.strip())
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def confirm_order(*, actor_user_id, order_id, version):
    try:
        if type(version) is not int or not 1 <= version <= 2147483647:
            raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv.")
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.ACHIZITII:
            raise OrderManagementForbiddenError("Doar achizitiile pot confirma comenzi.")
        order = db.session.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id)
                                  .with_for_update().execution_options(populate_existing=True))
        if order is None:
            raise OrderNotFoundError("Comanda nu a fost gasita.")
        if order.status != "DRAFT":
            raise OrderConflictError("Doar ciornele pot fi confirmate.")
        if order.version != version or version == 2147483647:
            raise OrderConflictError("Comanda a fost modificata. Reincarca datele inainte de confirmare.")
        if not order.items:
            raise ValueError("Comanda trebuie sa aiba cel putin o pozitie pentru confirmare.")
        values = [{key: value for key, value in item_data(item).items()
                   if key in {"product_id", "quantity", "unit_price", "vat_rate", "expected_date"}} for item in order.items]
        parsed = parse_order(order.supplier_id, order.currency, values)
        products = lock_catalog(order.supplier_id, parsed)
        if any(item.unit != products[item.product_id].unit for item in order.items):
            raise ValueError("Unitatea unei pozitii nu corespunde produsului din catalog.")
        before = order_data(order, include_items=False)
        order.status = "CONFIRMED"
        order.confirmed_at = datetime.now(timezone.utc)
        order.version += 1
        result = order_data(order)
        record_audit(action="CONFIRM", entity_type="purchase_orders", entity_id=order.id, actor_user_id=actor.id,
                     before={key: value for key, value in before.items() if key != "id"},
                     after={key: value for key, value in result.items() if key not in {"id", "items"}})
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def visible_orders(role):
    if role == Role.ACHIZITII:
        return []
    if role in (Role.DEPOZIT, Role.CONTABILITATE):
        return [PurchaseOrder.status.in_(("CONFIRMED", "CLOSED")), PurchaseOrder.confirmed_at.is_not(None)]
    raise OrderManagementForbiddenError("Rolul nu permite consultarea comenzilor.")


def header_columns(role):
    fields = [PurchaseOrder.id, PurchaseOrder.number, PurchaseOrder.supplier_id, PurchaseOrder.status,
              PurchaseOrder.version, PurchaseOrder.confirmed_at]
    if role != Role.DEPOZIT:
        fields.extend([PurchaseOrder.currency, PurchaseOrder.owner_id, PurchaseOrder.created_by_id])
    return fields


def read_header(row):
    result = dict(row._mapping)
    value = result["confirmed_at"]
    result["confirmed_at"] = value.astimezone(timezone.utc).isoformat() if value else None
    return result


def get_order(order_id, *, role=Role.ACHIZITII):
    conditions = visible_orders(role)
    row = db.session.execute(select(*header_columns(role)).where(PurchaseOrder.id == order_id, *conditions)).first()
    if row is None:
        raise OrderNotFoundError("Comanda nu a fost gasita.")
    result = read_header(row)
    fields = [PurchaseOrderItem.id, PurchaseOrderItem.line_number, PurchaseOrderItem.product_id,
              PurchaseOrderItem.description, PurchaseOrderItem.unit, PurchaseOrderItem.quantity, PurchaseOrderItem.expected_date]
    if role != Role.DEPOZIT:
        fields.extend([PurchaseOrderItem.unit_price, PurchaseOrderItem.vat_rate])
    rows = db.session.execute(select(*fields).where(PurchaseOrderItem.purchase_order_id == order_id).order_by(PurchaseOrderItem.line_number))
    result["items"] = []
    for row in rows:
        item = dict(row._mapping)
        item["quantity"] = format(item["quantity"], ".3f")
        item["expected_date"] = item["expected_date"].isoformat()
        if role != Role.DEPOZIT:
            item["unit_price"] = format(item["unit_price"], ".4f")
            item["vat_rate"] = format(item["vat_rate"], ".2f")
        result["items"].append(item)
    return result


def accepted_quantities_subquery():
    return (
        select(ReceiptItem.purchase_order_item_id.label("order_item_id"),
               func.sum(ReceiptItem.accepted_quantity).label("accepted_quantity"))
        .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
        .where(Receipt.status == "CONFIRMED")
        .group_by(ReceiptItem.purchase_order_item_id)
        .subquery()
    )


def get_order_delivery(order_id, *, role=Role.ACHIZITII):
    order = get_order(order_id, role=role)
    accepted_totals = accepted_quantities_subquery()
    rows = db.session.execute(
        select(PurchaseOrderItem.id, func.coalesce(accepted_totals.c.accepted_quantity, 0))
        .outerjoin(accepted_totals, accepted_totals.c.order_item_id == PurchaseOrderItem.id)
        .where(PurchaseOrderItem.purchase_order_id == order_id)
    )
    accepted_by_line = dict(rows.all())
    items = []
    for item in order["items"]:
        ordered = Decimal(item["quantity"])
        accepted = accepted_by_line.get(item["id"], Decimal("0"))
        remaining = ordered - accepted
        status = "NOT_RECEIVED" if accepted == 0 else "PARTIAL" if remaining > 0 else "COMPLETE"
        items.append({key: item[key] for key in (
            "id", "line_number", "product_id", "description", "unit", "quantity", "expected_date",
        )})
        items[-1].update(accepted_quantity=format(accepted, ".3f"), remaining_quantity=format(remaining, ".3f"), delivery_status=status)
    status = delivery_status(len(items), sum(item["delivery_status"] != "COMPLETE" for item in items),
                             sum(Decimal(item["accepted_quantity"]) > 0 for item in items))
    return {"id": order["id"], "number": order["number"], "status": order["status"],
            "delivery_status": status if order["status"] in ("CONFIRMED", "CLOSED") else None, "items": items}


def delivery_status(total_lines, remaining_lines, accepted_lines):
    if not total_lines:
        return None
    if not remaining_lines:
        return "COMPLETE"
    return "PARTIAL" if accepted_lines else "NOT_RECEIVED"


def get_order_invoicing(order_id):
    order = get_order(order_id, role=Role.CONTABILITATE)
    delivery = get_order_delivery(order_id, role=Role.CONTABILITATE)
    ids = [item["id"] for item in order["items"]]
    registered = {}
    documents = {}
    invoice_lines = db.session.execute(select(Invoice.id, Invoice.series, Invoice.number, Invoice.status,
        InvoiceItem.purchase_order_item_id, InvoiceItem.quantity)
        .join(InvoiceItem, InvoiceItem.invoice_id == Invoice.id)
        .where(InvoiceItem.purchase_order_item_id.in_(ids)).order_by(Invoice.id, InvoiceItem.line_number))
    for row in invoice_lines:
        if row.status != "CANCELLED":
            registered[row.purchase_order_item_id] = registered.get(row.purchase_order_item_id, Decimal("0")) + row.quantity
        document = documents.setdefault(row.id, {"id": row.id, "series": row.series, "number": row.number,
            "status": row.status, "items": []})
        document["items"].append({"purchase_order_item_id": row.purchase_order_item_id, "quantity": format(row.quantity, ".3f")})
    manual_lines = db.session.execute(select(Invoice.id, Invoice.series, Invoice.number, Invoice.status,
        ReceiptItem.purchase_order_item_id, func.sum(InvoiceAllocation.quantity).label("quantity"))
        .select_from(InvoiceAllocation).join(InvoiceItem, InvoiceItem.id == InvoiceAllocation.invoice_item_id)
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id).join(ReceiptItem, ReceiptItem.id == InvoiceAllocation.receipt_item_id)
        .where(InvoiceItem.purchase_order_item_id.is_(None), Invoice.status != "CANCELLED", ReceiptItem.purchase_order_item_id.in_(ids), InvoiceAllocation.status == "ACTIVE")
        .group_by(Invoice.id, Invoice.series, Invoice.number, Invoice.status, ReceiptItem.purchase_order_item_id)
        .order_by(Invoice.id, ReceiptItem.purchase_order_item_id))
    for row in manual_lines:
        registered[row.purchase_order_item_id] = registered.get(row.purchase_order_item_id, Decimal("0")) + row.quantity
        document = documents.setdefault(row.id, {"id": row.id, "series": row.series, "number": row.number,
            "status": row.status, "items": []})
        document["items"].append({"purchase_order_item_id": row.purchase_order_item_id,
            "quantity": format(row.quantity, ".3f"), "via_receipts": True})
    order["invoice_documents"] = [documents[key] for key in sorted(documents)]
    allocated = dict(db.session.execute(select(ReceiptItem.purchase_order_item_id, func.sum(InvoiceAllocation.quantity))
        .join(InvoiceAllocation, InvoiceAllocation.receipt_item_id == ReceiptItem.id)
        .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
        .where(ReceiptItem.purchase_order_item_id.in_(ids), Receipt.status == "CONFIRMED", InvoiceAllocation.status == "ACTIVE")
        .group_by(ReceiptItem.purchase_order_item_id)).all())
    delivery_by_id = {item["id"]: item for item in delivery["items"]}
    for item in order["items"]:
        accepted = Decimal(delivery_by_id[item["id"]]["accepted_quantity"])
        used = allocated.get(item["id"], Decimal("0"))
        item.update(accepted_quantity=format(accepted, ".3f"), allocated_quantity=format(used, ".3f"),
                    available_quantity=format(max(accepted - used, Decimal("0")), ".3f"),
                    registered_quantity=format(registered.get(item["id"], Decimal("0")), ".3f"),
                    remaining_to_invoice=format(max(Decimal(item["quantity"]) - registered.get(item["id"], Decimal("0")), Decimal("0")), ".3f"))
    return order


def bucharest_date(moment=None):
    return db.session.scalar(select(func.timezone("Europe/Bucharest", moment if moment is not None else func.now()).cast(Date)))


def overdue_items_query(today, *, role=Role.ACHIZITII):
    conditions = visible_orders(role)
    accepted_totals = accepted_quantities_subquery()
    accepted = func.coalesce(accepted_totals.c.accepted_quantity, 0)
    remaining = PurchaseOrderItem.quantity - accepted
    return (
        select(PurchaseOrder.id.label("order_id"), PurchaseOrder.number.label("order_number"), PurchaseOrder.supplier_id,
               PurchaseOrderItem.id, PurchaseOrderItem.line_number, PurchaseOrderItem.product_id,
               PurchaseOrderItem.description, PurchaseOrderItem.unit, PurchaseOrderItem.quantity, PurchaseOrderItem.expected_date,
               accepted.label("accepted_quantity"), remaining.label("remaining_quantity"))
        .join(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .outerjoin(accepted_totals, accepted_totals.c.order_item_id == PurchaseOrderItem.id)
        .where(*conditions, PurchaseOrder.status == "CONFIRMED", PurchaseOrder.confirmed_at.is_not(None),
               PurchaseOrderItem.expected_date < today, remaining > 0)
    )


def list_overdue_items(*, page, per_page, role=Role.ACHIZITII):
    today = bucharest_date()
    query = (overdue_items_query(today, role=role).add_columns(Supplier.name.label("supplier_name"))
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id))
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.session.execute(query.order_by(PurchaseOrderItem.expected_date, PurchaseOrder.id, PurchaseOrderItem.line_number)
                              .offset((page - 1) * per_page).limit(per_page))
    items = []
    for row in rows:
        item = dict(row._mapping)
        item["days_overdue"] = (today - row.expected_date).days
        item["expected_date"] = row.expected_date.isoformat()
        for key in ("quantity", "accepted_quantity", "remaining_quantity"):
            item[key] = format(item[key], ".3f")
        items.append(item)
    return {"items": items, "page": page, "per_page": per_page, "total": total,
            "as_of": today.isoformat(), "timezone": "Europe/Bucharest"}


def list_orders(*, page, per_page, role=Role.ACHIZITII):
    conditions = visible_orders(role)
    accepted_totals = accepted_quantities_subquery()
    accepted = func.coalesce(accepted_totals.c.accepted_quantity, 0)
    remaining = PurchaseOrderItem.quantity > accepted
    progress = select(PurchaseOrderItem.purchase_order_id.label("order_id"),
        func.count().filter(remaining).label("remaining_lines"),
        func.count().filter(accepted > 0).label("received_lines"),
        func.min(PurchaseOrderItem.expected_date).filter(remaining).label("next_deadline"))\
        .outerjoin(accepted_totals, accepted_totals.c.order_item_id == PurchaseOrderItem.id)\
        .group_by(PurchaseOrderItem.purchase_order_id).subquery()
    open_order = PurchaseOrder.status == "CONFIRMED"
    priority = case((open_order & (progress.c.next_deadline < bucharest_date()), 0),
        (PurchaseOrder.status == "DRAFT", 1),
        (open_order & (progress.c.remaining_lines > 0) & (progress.c.received_lines > 0), 2),
        (open_order & (progress.c.remaining_lines > 0), 3),
        (PurchaseOrder.status == "CONFIRMED", 4), (PurchaseOrder.status == "CLOSED", 5), else_=6)
    rows = db.session.execute(select(*header_columns(role), Supplier.name.label("supplier_name"))
                              .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
                              .outerjoin(progress, progress.c.order_id == PurchaseOrder.id).where(*conditions)
                              .order_by(priority, progress.c.next_deadline.asc().nulls_last(), PurchaseOrder.id)
                              .offset((page - 1) * per_page).limit(per_page))
    orders = [read_header(row) for row in rows]
    by_id = {order["id"]: order for order in orders}
    for order in orders:
        order["items"] = []
    fields = [PurchaseOrderItem.purchase_order_id, PurchaseOrderItem.id, PurchaseOrderItem.line_number,
              PurchaseOrderItem.product_id, Product.sku, PurchaseOrderItem.description, PurchaseOrderItem.unit,
              PurchaseOrderItem.quantity]
    if role != Role.DEPOZIT:
        fields.append(PurchaseOrderItem.unit_price)
    lines = db.session.execute(select(*fields).join(Product, Product.id == PurchaseOrderItem.product_id)
        .where(PurchaseOrderItem.purchase_order_id.in_(by_id))
        .order_by(PurchaseOrderItem.purchase_order_id, PurchaseOrderItem.line_number)).all() if orders else []
    for row in lines:
        item = dict(row._mapping)
        order_id = item.pop("purchase_order_id")
        item["quantity"] = format(item["quantity"], ".3f")
        if role != Role.DEPOZIT:
            item["unit_price"] = format(item["unit_price"], ".4f")
        by_id[order_id]["items"].append(item)
    accepted_totals = accepted_quantities_subquery()
    accepted = func.coalesce(accepted_totals.c.accepted_quantity, 0)
    summaries = db.session.execute(select(PurchaseOrderItem.purchase_order_id, func.count(),
        func.count().filter(PurchaseOrderItem.quantity > accepted), func.count().filter(accepted > 0))
        .outerjoin(accepted_totals, accepted_totals.c.order_item_id == PurchaseOrderItem.id)
        .where(PurchaseOrderItem.purchase_order_id.in_([order["id"] for order in orders]))
        .group_by(PurchaseOrderItem.purchase_order_id)).all() if orders else []
    states = {order_id: delivery_status(total, remaining, received) for order_id, total, remaining, received in summaries}
    for order in orders:
        order["delivery_status"] = states.get(order["id"]) if order["status"] in ("CONFIRMED", "CLOSED") else None
    return {"orders": orders, "page": page, "per_page": per_page,
            "total": db.session.scalar(select(func.count()).select_from(PurchaseOrder).where(*conditions))}
