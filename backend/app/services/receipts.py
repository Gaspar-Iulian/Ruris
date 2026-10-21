from datetime import datetime, timezone
from decimal import Decimal
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import raiseload

from app.extensions import db
from app.models import PurchaseOrder, PurchaseOrderItem, Receipt, ReceiptItem, Role, User
from app.models import Product, StockMovement, Supplier
from app.services.audit import record_audit
from app.services.purchase_orders import decimal_value, positive_id


class ReceiptCreationForbiddenError(PermissionError):
    pass


class ReceiptNotFoundError(LookupError):
    pass


class ReceiptSourceConflictError(ValueError):
    pass


class ReceiptManagementForbiddenError(PermissionError):
    pass


class ReceiptConflictError(ValueError):
    pass


def parse_receipt_header(delivery_reference, received_at):
    if not isinstance(delivery_reference, str) or not 1 <= len(delivery_reference.strip()) <= 120:
        raise ValueError("Referinta documentului de livrare trebuie sa aiba intre 1 si 120 de caractere.")
    if not isinstance(received_at, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", received_at
    ):
        raise ValueError("Data receptiei trebuie sa fie ISO 8601, cu ora si fus orar explicit.")
    try:
        received = datetime.fromisoformat(received_at).astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise ValueError("Data receptiei nu este valida.") from error
    return delivery_reference.strip(), received


def receipt_data(receipt, *, include_items=True):
    data = {key: getattr(receipt, key) for key in (
        "id", "number", "supplier_id", "delivery_reference", "status", "created_by_id", "confirmed_by_id", "version",
    )}
    data["received_at"] = receipt.received_at.astimezone(timezone.utc).isoformat()
    data["confirmed_at"] = receipt.confirmed_at.astimezone(timezone.utc).isoformat() if receipt.confirmed_at else None
    if include_items:
        data["items"] = [receipt_item_data(item) for item in receipt.items]
    return data


def receipt_item_data(item):
    data = {key: getattr(item, key) for key in (
        "id", "line_number", "product_id", "purchase_order_item_id", "description", "unit",
        "pending_order_item_id", "origin_item_id",
    )}
    for key in ("received_quantity", "accepted_quantity", "rejected_quantity", "pending_quantity", "resolved_quantity"):
        data[key] = format(getattr(item, key), ".3f")
    return data


def create_receipt(*, actor_user_id, purchase_order_id, delivery_reference, received_at, items):
    try:
        positive_id(purchase_order_id)
        reference, received = parse_receipt_header(delivery_reference, received_at)
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("Receptia trebuie sa contina intre 1 si 100 de pozitii.")
        parsed = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"purchase_order_item_id", "received_quantity"}:
                raise ValueError("Fiecare pozitie necesita purchase_order_item_id si received_quantity.")
            parsed.append((positive_id(item["purchase_order_item_id"]),
                           decimal_value(item["received_quantity"], scale=3, integer_digits=15, positive=True)))
        item_ids = [item_id for item_id, quantity in parsed]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("O pozitie de comanda poate aparea o singura data in receptie.")
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.DEPOZIT:
            raise ReceiptCreationForbiddenError("Doar depozitul poate crea receptii.")
        source = db.session.execute(select(PurchaseOrder.id, PurchaseOrder.supplier_id, PurchaseOrder.status, PurchaseOrder.confirmed_at)
                                     .where(PurchaseOrder.id == purchase_order_id).with_for_update()).first()
        if source is None:
            raise ReceiptNotFoundError("Comanda nu a fost gasita.")
        if source.status != "CONFIRMED" or source.confirmed_at is None:
            raise ReceiptSourceConflictError("Receptia necesita o comanda confirmata si deschisa.")
        rows = db.session.execute(select(PurchaseOrderItem.id, PurchaseOrderItem.product_id, PurchaseOrderItem.description, PurchaseOrderItem.unit)
                                   .where(PurchaseOrderItem.purchase_order_id == purchase_order_id, PurchaseOrderItem.id.in_(item_ids))
                                   .order_by(PurchaseOrderItem.id).with_for_update()).all()
        by_id = {row.id: row for row in rows}
        if len(by_id) != len(item_ids):
            raise ValueError("Toate pozitiile trebuie sa apartina comenzii selectate.")
        receipt = Receipt(supplier_id=source.supplier_id, delivery_reference=reference,
                          received_at=received, created_by_id=actor.id)
        for line, (item_id, quantity) in enumerate(parsed, 1):
            item = by_id[item_id]
            receipt.items.append(ReceiptItem(line_number=line, product_id=item.product_id, purchase_order_item_id=item_id,
                                             description=item.description, unit=item.unit, received_quantity=quantity, pending_quantity=quantity))
        db.session.add(receipt)
        db.session.flush()
        result = receipt_data(receipt)
        record_audit(action="CREATE", entity_type="receipts", entity_id=receipt.id, actor_user_id=actor.id,
                     after={key: value for key, value in result.items() if key not in {"id", "items"}})
        for item in receipt.items:
            record_audit(action="CREATE", entity_type="receipt_items", entity_id=item.id, actor_user_id=actor.id,
                         after={"receipt_id": receipt.id, **{key: value for key, value in receipt_item_data(item).items() if key != "id"}})
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def edit_receipt(*, actor_user_id, receipt_id, version, reason, delivery_reference, received_at, items):
    try:
        if type(version) is not int or not 1 <= version <= 2147483647:
            raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        reference, received = parse_receipt_header(delivery_reference, received_at)
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("Trimite lista completa cu 1-100 de pozitii existente.")
        quantities = {}
        for item in items:
            if not isinstance(item, dict) or set(item) != {"id", "received_quantity"}:
                raise ValueError("Fiecare pozitie necesita doar id si received_quantity.")
            item_id = positive_id(item["id"])
            if item_id in quantities:
                raise ValueError("O pozitie poate aparea o singura data.")
            quantities[item_id] = decimal_value(item["received_quantity"], scale=3, integer_digits=15, positive=True)
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.DEPOZIT:
            raise ReceiptManagementForbiddenError("Doar depozitul poate modifica receptii.")
        receipt = db.session.scalar(select(Receipt).where(Receipt.id == receipt_id).with_for_update().execution_options(populate_existing=True))
        if receipt is None:
            raise ReceiptNotFoundError("Receptia nu a fost gasita.")
        if receipt.status != "DRAFT" or receipt.confirmed_at is not None or receipt.confirmed_by_id is not None:
            raise ReceiptConflictError("Doar ciornele neconfirmate pot fi modificate.")
        if receipt.version != version or version == 2147483647:
            raise ReceiptConflictError("Receptia a fost modificata. Reincarca datele inainte de salvare.")
        if set(quantities) != {item.id for item in receipt.items}:
            raise ValueError("Trimite exact pozitiile existente ale acestei receptii.")
        if any(item.accepted_quantity != 0 or item.rejected_quantity != 0 for item in receipt.items):
            raise ReceiptConflictError("Cantitatile deja clasificate necesita o operatie separata de corectie.")
        before = receipt_data(receipt)
        before_items = {item["id"]: item for item in before["items"]}
        receipt.delivery_reference = reference
        receipt.received_at = received
        for item in receipt.items:
            item.received_quantity = quantities[item.id]
            item.pending_quantity = quantities[item.id]
        result = receipt_data(receipt)
        if result != before:
            receipt.version += 1
            result["version"] = receipt.version
            record_audit(action="UPDATE", entity_type="receipts", entity_id=receipt.id, actor_user_id=actor.id,
                         before={key: value for key, value in before.items() if key not in {"id", "items"}},
                         after={key: value for key, value in result.items() if key not in {"id", "items"}}, reason=reason.strip())
            for item in result["items"]:
                previous = before_items[item["id"]]
                if previous != item:
                    record_audit(action="UPDATE", entity_type="receipt_items", entity_id=item["id"], actor_user_id=actor.id,
                                 before={"receipt_id": receipt.id, **{key: value for key, value in previous.items() if key != "id"}},
                                 after={"receipt_id": receipt.id, **{key: value for key, value in item.items() if key != "id"}}, reason=reason.strip())
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def confirm_receipt(*, actor_user_id, receipt_id, version, reason, items):
    try:
        if type(version) is not int or not 1 <= version <= 2147483647:
            raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("Trimite toate pozitiile receptiei, intre 1 si 100.")
        quantities = {}
        fields = {"id", "accepted_quantity", "rejected_quantity", "pending_quantity"}
        for item in items:
            if not isinstance(item, dict) or set(item) != fields:
                raise ValueError("Fiecare pozitie necesita id, accepted_quantity, rejected_quantity si pending_quantity.")
            item_id = positive_id(item["id"])
            if item_id in quantities:
                raise ValueError("Pozitiile nu pot fi duplicate.")
            quantities[item_id] = {key: decimal_value(item[key], scale=3, integer_digits=15) for key in fields - {"id"}}
        actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.role != Role.DEPOZIT:
            raise ReceiptManagementForbiddenError("Doar depozitul poate confirma receptii.")
        receipt = db.session.scalar(select(Receipt).where(Receipt.id == receipt_id).with_for_update().execution_options(populate_existing=True))
        if receipt is None:
            raise ReceiptNotFoundError("Receptia nu a fost gasita.")
        if receipt.status != "DRAFT" or receipt.confirmed_at is not None or receipt.confirmed_by_id is not None:
            raise ReceiptConflictError("Doar ciornele neconfirmate pot fi confirmate.")
        if receipt.version != version or version == 2147483647:
            raise ReceiptConflictError("Receptia a fost modificata. Reincarca datele inainte de confirmare.")
        if set(quantities) != {item.id for item in receipt.items}:
            raise ValueError("Trimite exact pozitiile acestei receptii.")
        if any(item.accepted_quantity != 0 or item.rejected_quantity != 0 for item in receipt.items):
            raise ReceiptConflictError("Ciorna contine cantitati deja clasificate.")
        for item in receipt.items:
            if sum(quantities[item.id].values(), Decimal("0")) != item.received_quantity:
                raise ValueError("Cantitatea sosita trebuie sa fie egala cu acceptata + respinsa + in asteptare.")
        accepting = [item for item in receipt.items if quantities[item.id]["accepted_quantity"] > 0]
        if any(item.purchase_order_item_id is None for item in accepting):
            raise ValueError("Acceptarea necesita o pozitie de comanda.")
        source_ids = sorted({item.purchase_order_item_id for item in accepting})
        order_ids = db.session.scalars(select(PurchaseOrderItem.purchase_order_id)
                                       .where(PurchaseOrderItem.id.in_(source_ids)).distinct()).all()
        orders = db.session.execute(select(PurchaseOrder.id, PurchaseOrder.supplier_id, PurchaseOrder.status, PurchaseOrder.confirmed_at)
                                    .where(PurchaseOrder.id.in_(order_ids)).order_by(PurchaseOrder.id).with_for_update()).all()
        orders_by_id = {order.id: order for order in orders}
        sources = db.session.execute(select(PurchaseOrderItem.id, PurchaseOrderItem.purchase_order_id, PurchaseOrderItem.product_id,
                                             PurchaseOrderItem.unit, PurchaseOrderItem.quantity)
                                     .where(PurchaseOrderItem.id.in_(source_ids)).order_by(PurchaseOrderItem.id).with_for_update()).all()
        by_id = {source.id: source for source in sources}
        products = db.session.execute(select(Product.id, Product.is_active, Product.unit)
                                      .where(Product.id.in_({item.product_id for item in accepting})).order_by(Product.id).with_for_update()).all()
        products_by_id = {product.id: product for product in products}
        accepted_rows = db.session.execute(select(ReceiptItem.purchase_order_item_id, func.sum(ReceiptItem.accepted_quantity))
                                           .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
                                           .where(Receipt.status == "CONFIRMED", ReceiptItem.purchase_order_item_id.in_(source_ids))
                                           .group_by(ReceiptItem.purchase_order_item_id)).all()
        used = {source_id: quantity for source_id, quantity in accepted_rows}
        for item in accepting:
            source = by_id.get(item.purchase_order_item_id)
            order = orders_by_id.get(source.purchase_order_id) if source else None
            product = products_by_id.get(item.product_id)
            if (source is None or order is None or order.status != "CONFIRMED" or order.confirmed_at is None
                    or order.supplier_id != receipt.supplier_id or source.product_id != item.product_id or source.unit != item.unit
                    or product is None or not product.is_active or product.unit != item.unit):
                raise ReceiptConflictError("Acceptarea necesita comanda deschisa, furnizor/produs/unitate compatibile si produs activ.")
            total = used.get(source.id, Decimal("0")) + quantities[item.id]["accepted_quantity"]
            if total > source.quantity:
                raise ReceiptConflictError("Cantitatea acceptata depaseste restul de livrat al pozitiei de comanda.")
            used[source.id] = total
        before = receipt_data(receipt)
        previous_items = {item["id"]: item for item in before["items"]}
        receipt.status = "CONFIRMED"
        receipt.confirmed_at = datetime.now(timezone.utc)
        receipt.confirmed_by_id = actor.id
        receipt.version += 1
        for item in receipt.items:
            for key, value in quantities[item.id].items():
                setattr(item, key, value)
            if item.accepted_quantity > 0:
                movement = StockMovement(product_id=item.product_id, receipt_item_id=item.id, kind="RECEIPT",
                                         quantity_delta=item.accepted_quantity, reason=reason.strip(), created_by_id=actor.id,
                                         operation_key=f"receipt:{receipt.id}:confirm:item:{item.id}")
                db.session.add(movement)
                db.session.flush()
                record_audit(action="CREATE", entity_type="stock_movements", entity_id=movement.id, actor_user_id=actor.id,
                             after={"product_id": movement.product_id, "receipt_item_id": movement.receipt_item_id,
                                    "kind": movement.kind, "quantity_delta": format(movement.quantity_delta, ".3f"),
                                    "reason": movement.reason, "created_by_id": actor.id, "operation_key": movement.operation_key}, reason=reason.strip())
        result = receipt_data(receipt)
        record_audit(action="CONFIRM", entity_type="receipts", entity_id=receipt.id, actor_user_id=actor.id,
                     before={key: value for key, value in before.items() if key not in {"id", "items"}},
                     after={key: value for key, value in result.items() if key not in {"id", "items"}}, reason=reason.strip())
        for item in result["items"]:
            previous = previous_items[item["id"]]
            if previous != item:
                record_audit(action="UPDATE", entity_type="receipt_items", entity_id=item["id"], actor_user_id=actor.id,
                             before={"receipt_id": receipt.id, **{key: value for key, value in previous.items() if key != "id"}},
                             after={"receipt_id": receipt.id, **{key: value for key, value in item.items() if key != "id"}}, reason=reason.strip())
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def visible_receipts(role):
    if role == Role.DEPOZIT:
        return []
    if role in (Role.ACHIZITII, Role.CONTABILITATE):
        return [Receipt.status == "CONFIRMED", Receipt.confirmed_at.is_not(None), Receipt.confirmed_by_id.is_not(None)]
    raise ReceiptManagementForbiddenError("Rolul nu permite consultarea receptiilor.")


def get_receipt(receipt_id, *, role=Role.DEPOZIT):
    receipt = db.session.scalar(select(Receipt).where(Receipt.id == receipt_id, *visible_receipts(role))
                                .execution_options(populate_existing=True))
    if receipt is None:
        raise ReceiptNotFoundError("Receptia nu a fost gasita.")
    if receipt.status != "CONFIRMED":
        return receipt_data(receipt)
    from app.services.receipt_exceptions import receipt_detail
    return receipt_detail(receipt)


def list_receipts(*, page, per_page, role=Role.DEPOZIT, pending_only=False):
    conditions = visible_receipts(role)
    if pending_only:
        conditions.extend([Receipt.status == "CONFIRMED", Receipt.confirmed_at.is_not(None), Receipt.confirmed_by_id.is_not(None),
                           select(ReceiptItem.id).where(ReceiptItem.receipt_id == Receipt.id,
                                                        ReceiptItem.origin_item_id.is_(None), ReceiptItem.pending_quantity > 0).exists()])
    receipts = db.session.scalars(select(Receipt).where(*conditions).options(raiseload(Receipt.items)).order_by(Receipt.id)
                                  .offset((page - 1) * per_page).limit(per_page)).all()
    pending = dict(db.session.execute(select(ReceiptItem.receipt_id, func.count())
        .where(ReceiptItem.receipt_id.in_([receipt.id for receipt in receipts]), ReceiptItem.origin_item_id.is_(None), ReceiptItem.pending_quantity > 0)
        .group_by(ReceiptItem.receipt_id)).all())
    suppliers = dict(db.session.execute(select(Supplier.id, Supplier.name)
        .where(Supplier.id.in_({receipt.supplier_id for receipt in receipts}))).all())
    lines = {receipt.id: [] for receipt in receipts}
    orders = {}
    sources = db.session.execute(select(func.coalesce(ReceiptItem.origin_item_id, ReceiptItem.id), PurchaseOrder.number)
        .join(PurchaseOrderItem, or_(PurchaseOrderItem.id == ReceiptItem.purchase_order_item_id,
                                    PurchaseOrderItem.id == ReceiptItem.pending_order_item_id))
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .where(ReceiptItem.receipt_id.in_(lines)).order_by(PurchaseOrder.id))
    for root_id, order_number in sources:
        orders.setdefault(root_id, {})[order_number] = None
    rows = db.session.scalars(select(ReceiptItem)
        .where(ReceiptItem.receipt_id.in_(lines), ReceiptItem.origin_item_id.is_(None))
        .order_by(ReceiptItem.receipt_id, ReceiptItem.line_number))
    for item in rows:
        lines[item.receipt_id].append({**receipt_item_data(item), "order_number": " / ".join(orders.get(item.id, {})) or None,
            "total_accepted_quantity": format(item.accepted_quantity + item.resolved_quantity, ".3f")})
    return {"receipts": [{**receipt_data(receipt, include_items=False), "supplier_name": suppliers[receipt.supplier_id],
                           "pending_count": pending.get(receipt.id, 0), "line_items": lines[receipt.id]} for receipt in receipts], "page": page, "per_page": per_page,
            "total": db.session.scalar(select(func.count()).select_from(Receipt).where(*conditions))}
