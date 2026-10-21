from decimal import Decimal

from sqlalchemy import and_, func, or_, select

from app.extensions import db
from app.models import AuditEvent, Product, PurchaseOrder, PurchaseOrderItem, Receipt, ReceiptItem, Role, StockMovement, Supplier, User
from app.services.audit import record_audit
from app.services.purchase_orders import decimal_value, positive_id
from app.services.receipts import ReceiptConflictError, ReceiptManagementForbiddenError, ReceiptNotFoundError
from app.services.receipts import parse_receipt_header, receipt_data, receipt_item_data, visible_receipts


def receipt_detail(receipt):
    result = receipt_data(receipt)
    ids = {value for item in receipt.items for value in (item.purchase_order_item_id, item.pending_order_item_id) if value is not None}
    sources = db.session.execute(select(PurchaseOrderItem.id, PurchaseOrder.number, Product.name)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .join(Product, Product.id == PurchaseOrderItem.product_id).where(PurchaseOrderItem.id.in_(ids))).all() if ids else []
    by_source = {row.id: row for row in sources}
    originals = [item for item in receipt.items if item.origin_item_id is None]
    result["items"] = []
    for item in originals:
        data = receipt_item_data(item)
        data["total_accepted_quantity"] = format(item.accepted_quantity + item.resolved_quantity, ".3f")
        source = by_source.get(item.pending_order_item_id or item.purchase_order_item_id)
        data["pending_order_number"] = source.number if source else None
        data["pending_product_name"] = source.name if source else None
        data["acceptances"] = [
            {**receipt_item_data(child), "order_number": by_source[child.purchase_order_item_id].number,
             "product_name": by_source[child.purchase_order_item_id].name}
            for child in receipt.items if child.origin_item_id == item.id
        ]
        result["items"].append(data)
    result["supplier_name"] = db.session.scalar(select(Supplier.name).where(Supplier.id == receipt.supplier_id))
    return result


def _actor(actor_user_id, role):
    actor = db.session.scalar(select(User).where(User.id == actor_user_id).with_for_update().execution_options(populate_existing=True))
    if actor is None or not actor.is_active or actor.role != role:
        raise ReceiptManagementForbiddenError("Echipa sau contul nu permite aceasta operatie.")
    return actor


def _pending_item(receipt_id, item_id, version, reason):
    positive_id(receipt_id)
    positive_id(item_id)
    if type(version) is not int or not 1 <= version < 2147483647:
        raise ValueError("Versiunea trebuie sa fie un numar intreg pozitiv sub 2147483647.")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
        raise ValueError("Completeaza observatii de 1-1000 de caractere.")
    receipt = db.session.scalar(select(Receipt).where(Receipt.id == receipt_id).with_for_update().execution_options(populate_existing=True))
    if receipt is None:
        raise ReceiptNotFoundError("Receptia nu a fost gasita.")
    if (receipt.status != "CONFIRMED" or receipt.confirmed_at is None or receipt.confirmed_by_id is None
            or receipt.version != version):
        raise ReceiptConflictError("Receptia nu este confirmata sau a fost modificata. Actualizeaza datele.")
    item = db.session.scalar(select(ReceiptItem).where(ReceiptItem.id == item_id, ReceiptItem.receipt_id == receipt.id)
                             .with_for_update().execution_options(populate_existing=True))
    if item is None or item.origin_item_id is not None:
        raise ReceiptNotFoundError("Pozitia sosita nu a fost gasita.")
    if item.pending_quantity <= 0:
        raise ReceiptConflictError("Pozitia nu mai are cantitate in asteptare.")
    return receipt, item


def _source(receipt, item, source_id):
    positive_id(source_id)
    order_id = db.session.scalar(select(PurchaseOrderItem.purchase_order_id).where(PurchaseOrderItem.id == source_id))
    order = db.session.execute(select(PurchaseOrder.id, PurchaseOrder.supplier_id, PurchaseOrder.status, PurchaseOrder.confirmed_at)
                               .where(PurchaseOrder.id == order_id).with_for_update()).first()
    source = db.session.execute(select(PurchaseOrderItem.id, PurchaseOrderItem.product_id, PurchaseOrderItem.unit, PurchaseOrderItem.quantity)
                                .where(PurchaseOrderItem.id == source_id).with_for_update()).first()
    product = None if source is None else db.session.execute(select(Product.id, Product.unit, Product.is_active)
        .where(Product.id == source.product_id).with_for_update()).first()
    if (order is None or source is None or order.status != "CONFIRMED" or order.confirmed_at is None
            or order.supplier_id != receipt.supplier_id or source.unit != item.unit
            or (item.product_id is not None and source.product_id != item.product_id)
            or product is None or not product.is_active or product.unit != item.unit):
        raise ReceiptConflictError("Selecteaza o comanda deschisa, cu acelasi furnizor, produs compatibil si aceeasi unitate.")
    used = db.session.scalar(select(func.coalesce(func.sum(ReceiptItem.accepted_quantity), 0))
        .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
        .where(Receipt.status == "CONFIRMED", ReceiptItem.purchase_order_item_id == source_id))
    return source, source.quantity - used


def _audit_item(item, actor_id, action, reason, before=None):
    record_audit(action=action, entity_type="receipt_items", entity_id=item.id, actor_user_id=actor_id,
                 before=before, after={"receipt_id": item.receipt_id, **{key: value for key, value in receipt_item_data(item).items() if key != "id"}},
                 reason=reason)


def _finish(receipt, actor_id, before, reason):
    receipt.version += 1
    record_audit(action="UPDATE", entity_type="receipts", entity_id=receipt.id, actor_user_id=actor_id,
                 before=before, after={key: value for key, value in receipt_data(receipt, include_items=False).items() if key != "id"}, reason=reason)
    db.session.flush()
    result = receipt_detail(receipt)
    db.session.commit()
    return result


def create_unordered_receipt(*, actor_user_id, supplier_id, delivery_reference, received_at, items):
    try:
        positive_id(supplier_id)
        reference, received = parse_receipt_header(delivery_reference, received_at)
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("Receptia trebuie sa aiba intre 1 si 100 de pozitii.")
        parsed = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"product_id", "description", "unit", "received_quantity"}:
                raise ValueError("Trimite product_id (sau null), description, unit si received_quantity pentru fiecare pozitie.")
            if item["product_id"] is not None:
                positive_id(item["product_id"])
            if not isinstance(item["description"], str) or not 1 <= len(item["description"].strip()) <= 200:
                raise ValueError("Descrierea produsului trebuie sa aiba intre 1 si 200 de caractere.")
            if item["unit"] not in ("BUC", "KG", "L", "M", "M2", "M3"):
                raise ValueError("Unitatea de masura nu este valida.")
            parsed.append({**item, "description": item["description"].strip(),
                           "received_quantity": decimal_value(item["received_quantity"], scale=3, integer_digits=15, positive=True)})
        actor = _actor(actor_user_id, Role.DEPOZIT)
        supplier = db.session.scalar(select(Supplier).where(Supplier.id == supplier_id).with_for_update().execution_options(populate_existing=True))
        if supplier is None or not supplier.is_active:
            raise ValueError("Selecteaza un furnizor activ.")
        products = {product.id: product for product in db.session.scalars(select(Product)
            .where(Product.id.in_({item["product_id"] for item in parsed if item["product_id"] is not None}))
            .order_by(Product.id).with_for_update().execution_options(populate_existing=True)).all()}
        for item in parsed:
            if item["product_id"] is not None:
                product = products.get(item["product_id"])
                if product is None or not product.is_active or product.unit != item["unit"]:
                    raise ValueError("Produsul trebuie sa fie activ si sa corespunda unitatii sosite.")
        receipt = Receipt(supplier_id=supplier_id, delivery_reference=reference, received_at=received, created_by_id=actor.id)
        for line, item in enumerate(parsed, 1):
            receipt.items.append(ReceiptItem(line_number=line, pending_quantity=item["received_quantity"], **item))
        db.session.add(receipt)
        db.session.flush()
        result = receipt_data(receipt)
        record_audit(action="CREATE", entity_type="receipts", entity_id=receipt.id, actor_user_id=actor.id,
                     after={key: value for key, value in result.items() if key not in {"id", "items"}})
        for item in receipt.items:
            _audit_item(item, actor.id, "CREATE", None)
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def clarify_receipt_item(*, actor_user_id, receipt_id, item_id, version, reason, purchase_order_item_id):
    try:
        actor = _actor(actor_user_id, Role.ACHIZITII)
        receipt, item = _pending_item(receipt_id, item_id, version, reason)
        source, remaining = _source(receipt, item, purchase_order_item_id)
        if remaining <= 0:
            raise ReceiptConflictError("Pozitia comenzii nu mai are rest de livrat.")
        before = {key: value for key, value in receipt_data(receipt, include_items=False).items() if key != "id"}
        previous = {"receipt_id": receipt.id, **{key: value for key, value in receipt_item_data(item).items() if key != "id"}}
        item.pending_order_item_id = source.id
        _audit_item(item, actor.id, "CLARIFY", reason.strip(), before=previous)
        return _finish(receipt, actor.id, before, reason.strip())
    except Exception:
        db.session.rollback()
        raise


def resolve_receipt_item(*, actor_user_id, receipt_id, item_id, version, reason, action, quantity):
    try:
        if action not in ("ACCEPT", "REJECT"):
            raise ValueError("Decizia trebuie sa fie ACCEPT sau REJECT.")
        amount = decimal_value(quantity, scale=3, integer_digits=15, positive=True)
        actor = _actor(actor_user_id, Role.DEPOZIT)
        receipt, item = _pending_item(receipt_id, item_id, version, reason)
        if amount > item.pending_quantity:
            raise ReceiptConflictError("Cantitatea depaseste restul in asteptare.")
        source = None
        if action == "ACCEPT":
            source_id = item.pending_order_item_id or item.purchase_order_item_id
            if source_id is None:
                raise ReceiptConflictError("Achizitiile trebuie sa asocieze mai intai o comanda compatibila.")
            source, remaining = _source(receipt, item, source_id)
            if amount > remaining:
                raise ReceiptConflictError("Cantitatea acceptata depaseste restul de livrat al comenzii.")
        before = {key: value for key, value in receipt_data(receipt, include_items=False).items() if key != "id"}
        previous = {"receipt_id": receipt.id, **{key: value for key, value in receipt_item_data(item).items() if key != "id"}}
        item.pending_quantity -= amount
        if action == "REJECT":
            item.rejected_quantity += amount
        else:
            # Each acceptance keeps its own commercial source.
            item.resolved_quantity += amount
            child = ReceiptItem(receipt_id=receipt.id, line_number=max(line.line_number for line in receipt.items) + 1,
                                product_id=source.product_id, purchase_order_item_id=source.id, origin_item_id=item.id,
                                description=item.description, unit=item.unit, received_quantity=amount,
                                accepted_quantity=amount, pending_quantity=Decimal("0"))
            receipt.items.append(child)
            db.session.flush()
            _audit_item(child, actor.id, "CREATE", reason.strip())
            movement = StockMovement(product_id=source.product_id, receipt_item_id=child.id, kind="RECEIPT",
                                     quantity_delta=amount, reason=reason.strip(), created_by_id=actor.id,
                                     operation_key=f"receipt:{receipt.id}:resolve:{version + 1}:item:{item.id}")
            db.session.add(movement)
            db.session.flush()
            record_audit(action="CREATE", entity_type="stock_movements", entity_id=movement.id, actor_user_id=actor.id,
                         after={"product_id": movement.product_id, "receipt_item_id": child.id, "kind": "RECEIPT",
                                "quantity_delta": format(amount, ".3f"), "reason": reason.strip(), "created_by_id": actor.id,
                                "operation_key": movement.operation_key}, reason=reason.strip())
        _audit_item(item, actor.id, action, reason.strip(), before=previous)
        return _finish(receipt, actor.id, before, reason.strip())
    except Exception:
        db.session.rollback()
        raise


def receipt_history(receipt_id, *, role, page, per_page):
    receipt = db.session.scalar(select(Receipt).where(Receipt.id == receipt_id, *visible_receipts(role)))
    if receipt is None:
        raise ReceiptNotFoundError("Receptia nu a fost gasita.")
    by_id = {item.id: item for item in receipt.items}
    condition = or_(and_(AuditEvent.entity_type == "receipts", AuditEvent.entity_id == receipt_id),
                    and_(AuditEvent.entity_type == "receipt_items", AuditEvent.entity_id.in_(by_id)))
    rows = db.session.execute(select(AuditEvent, User.name).outerjoin(User, User.id == AuditEvent.actor_user_id)
        .where(condition).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset((page - 1) * per_page).limit(per_page)).all()
    source_ids = {source_id for event, _ in rows for snapshot in (event.before_data, event.after_data)
                  if snapshot for source_id in (snapshot.get("pending_order_item_id"), snapshot.get("purchase_order_item_id"))
                  if source_id is not None}
    sources = {row.id: row for row in db.session.execute(select(PurchaseOrderItem.id, PurchaseOrder.number, Product.name)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .join(Product, Product.id == PurchaseOrderItem.product_id).where(PurchaseOrderItem.id.in_(source_ids))).all()}
    events = []
    for event, name in rows:
        item = by_id.get(event.entity_id) if event.entity_type == "receipt_items" else None
        origin = by_id.get(item.origin_item_id) if item else None
        snapshot = event.after_data or {}
        source = sources.get(snapshot.get("pending_order_item_id") or snapshot.get("purchase_order_item_id"))
        events.append({"id": event.id, "action": event.action, "entity_type": event.entity_type,
                       "line_number": (origin or item).line_number if item else None,
                       "is_acceptance": bool(item and item.origin_item_id),
                       "actor_user_id": event.actor_user_id, "actor_name": name or event.actor_process,
                       "order_number": source.number if source else None, "product_name": source.name if source else None,
                       "created_at": event.created_at.isoformat(),
                       "reason": event.reason, "before": event.before_data, "after": event.after_data})
    return {"events": events, "total": db.session.scalar(select(func.count()).select_from(AuditEvent).where(condition)),
            "page": page, "per_page": per_page}
