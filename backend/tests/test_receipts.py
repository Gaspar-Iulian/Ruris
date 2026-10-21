from unittest.mock import patch

from flask import current_app
from flask_jwt_extended import create_access_token, get_csrf_token
import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models import AuditEvent, Product, PurchaseOrder, Receipt, ReceiptItem, Role, StockMovement, Supplier, User
from app.services.purchase_orders import confirm_order, create_order
from app.services.receipts import ReceiptCreationForbiddenError, create_receipt


@pytest.fixture
def setup(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    buyer = User(name="Achizitii", email="receipt-buyer@example.com", role=Role.ACHIZITII,
                 password_hash="unused", token_version=1, is_active=True)
    warehouse = User(name="Depozit", email="receipt-warehouse@example.com", role=Role.DEPOZIT,
                     password_hash="unused", token_version=1, is_active=True)
    supplier = Supplier(name="Furnizor", tax_country="RO", tax_id="123")
    product = Product(sku="P1", name="Produs comandat", unit="KG")
    session.add_all([buyer, warehouse, supplier, product])
    session.flush()
    values = {"buyer": buyer.id, "warehouse": warehouse.id, "supplier": supplier.id, "product": product.id}
    session.commit()
    order = create_order(actor_user_id=values["buyer"], supplier_id=values["supplier"], currency="RON", items=[{
        "product_id": values["product"], "quantity": "10.000", "unit_price": "2.0000",
        "vat_rate": "0.00", "expected_date": "2026-11-10",
    }])
    values["order"] = confirm_order(actor_user_id=values["buyer"], order_id=order["id"], version=1)
    return values


def authorize(user_id):
    token = create_access_token(identity=str(user_id), additional_claims={"token_version": 1})
    client = current_app.test_client()
    client.set_cookie("access_token_cookie", token, path="/api")
    return client, {"X-CSRF-TOKEN": get_csrf_token(token)}


def payload(setup, **changes):
    return {"purchase_order_id": setup["order"]["id"], "delivery_reference": " AVIZ-123 ",
            "received_at": "2026-10-20T10:30:00+03:00", "items": [{
                "purchase_order_item_id": setup["order"]["items"][0]["id"], "received_quantity": "3.125",
            }], **changes}


def assert_empty(session):
    assert session.scalar(select(func.count()).select_from(Receipt)) == 0
    assert session.scalar(select(func.count()).select_from(ReceiptItem)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type.in_(("receipts", "receipt_items")))) == 0


def test_partial_receipt_is_pending_and_audited(session, setup):
    client, headers = authorize(setup["warehouse"])
    response = client.post("/api/receipts", headers=headers, json=payload(setup))
    assert response.status_code == 201
    receipt = response.json["receipt"]
    assert receipt["number"] == f"REC-{receipt['id']}"
    assert receipt["supplier_id"] == setup["supplier"]
    assert receipt["delivery_reference"] == "AVIZ-123"
    assert receipt["received_at"] == "2026-10-20T07:30:00+00:00"
    assert receipt["created_by_id"] == setup["warehouse"]
    assert receipt["status"] == "DRAFT"
    assert receipt["version"] == 1
    assert receipt["confirmed_at"] is receipt["confirmed_by_id"] is None
    item = receipt["items"][0]
    assert item["description"] == "Produs comandat"
    assert item["unit"] == "KG"
    assert item["received_quantity"] == item["pending_quantity"] == "3.125"
    assert item["accepted_quantity"] == item["rejected_quantity"] == "0.000"
    events = session.scalars(select(AuditEvent).where(AuditEvent.entity_type.in_(("receipts", "receipt_items"))).order_by(AuditEvent.id)).all()
    assert len(events) == 2
    assert events[0].after_data == {key: value for key, value in receipt.items() if key not in {"id", "items"}}
    assert events[1].after_data == {"receipt_id": receipt["id"], **{key: value for key, value in item.items() if key != "id"}}
    assert all(event.actor_user_id == setup["warehouse"] for event in events)
    assert response.headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in response.headers
    assert client.get(f"/api/receipts/{receipt['id']}").json["receipt"] == receipt


def test_multiple_deliveries_and_surplus_do_not_change_order(session, setup):
    client, headers = authorize(setup["warehouse"])
    data = payload(setup)
    numbers = []
    for quantity in ("3", "2", "15"):
        data["items"][0]["received_quantity"] = quantity
        response = client.post("/api/receipts", headers=headers, json=data)
        assert response.status_code == 201
        assert response.json["receipt"]["items"][0]["accepted_quantity"] == "0.000"
        numbers.append(response.json["receipt"]["number"])
    assert len(set(numbers)) == 3
    order = session.get(PurchaseOrder, setup["order"]["id"])
    assert order.status == "CONFIRMED"
    assert order.version == 2
    listing = client.get("/api/receipts?page=2&per_page=1").json
    assert listing["total"] == 3
    assert listing["receipts"][0]["number"] == numbers[1]
    assert "items" not in listing["receipts"][0]


@pytest.mark.parametrize("role", [Role.ADMIN, Role.ACHIZITII, Role.CONTABILITATE])
def test_only_warehouse_can_access_receipt_drafts(session, setup, role):
    user = User(name="Alt rol", email="receipt-other@example.com", role=role,
                password_hash="unused", token_version=1, is_active=True)
    session.add(user)
    session.flush()
    user_id = user.id
    session.commit()
    client, headers = authorize(user_id)
    assert client.post("/api/receipts", headers=headers, json=payload(setup)).status_code == 403
    listing = client.get("/api/receipts")
    assert listing.status_code == (403 if role == Role.ADMIN else 200)
    if role != Role.ADMIN:
        assert listing.json["total"] == 0
        assert listing.json["receipts"] == []
    assert client.get("/api/receipts/1").status_code == (403 if role == Role.ADMIN else 404)
    assert_empty(session)


@pytest.mark.parametrize("changes", [
    {"purchase_order_id": True}, {"purchase_order_id": "1"}, {"delivery_reference": " "},
    {"delivery_reference": "x" * 121}, {"received_at": "2026-10-20"},
    {"received_at": "2026-10-20T10:30:00"}, {"received_at": "2026-02-30T10:30:00Z"},
    {"received_at": "2026-10-20T10:30:00+02:99"},
    {"received_at": None}, {"items": []}, {"items": None}, {"items": [None]},
    {"supplier_id": 1}, {"status": "CONFIRMED"},
])
def test_invalid_header_leaves_no_data(session, setup, changes):
    client, headers = authorize(setup["warehouse"])
    assert client.post("/api/receipts", headers=headers, json=payload(setup, **changes)).status_code == 400
    assert_empty(session)


@pytest.mark.parametrize("field,value", [
    ("received_quantity", "0"), ("received_quantity", "-1"), ("received_quantity", "1.0001"),
    ("received_quantity", "NaN"), ("received_quantity", 1.25), ("received_quantity", "1000000000000000"),
    ("purchase_order_item_id", True), ("purchase_order_item_id", 999),
    ("accepted_quantity", "1"), ("product_id", 1),
])
def test_invalid_line_leaves_no_data(session, setup, field, value):
    client, headers = authorize(setup["warehouse"])
    data = payload(setup)
    data["items"][0][field] = value
    assert client.post("/api/receipts", headers=headers, json=data).status_code == 400
    assert_empty(session)


@pytest.mark.parametrize("status", ["DRAFT", "CANCELLED", "CLOSED"])
def test_only_confirmed_open_orders_can_be_received(session, setup, status):
    session.get(PurchaseOrder, setup["order"]["id"]).status = status
    session.commit()
    client, headers = authorize(setup["warehouse"])
    assert client.post("/api/receipts", headers=headers, json=payload(setup)).status_code == 409
    assert_empty(session)


def test_duplicate_and_foreign_lines_are_rejected(session, setup):
    client, headers = authorize(setup["warehouse"])
    other = create_order(actor_user_id=setup["buyer"], supplier_id=setup["supplier"], currency="RON", items=[{
        "product_id": setup["product"], "quantity": "1", "unit_price": "1", "vat_rate": "0", "expected_date": "2026-11-10",
    }])
    data = payload(setup)
    data["items"] *= 2
    assert client.post("/api/receipts", headers=headers, json=data).status_code == 400
    data["items"] = [{"purchase_order_item_id": other["items"][0]["id"], "received_quantity": "1"}]
    assert client.post("/api/receipts", headers=headers, json=data).status_code == 400
    assert_empty(session)


def test_inactive_catalog_does_not_erase_physical_delivery(session, setup):
    session.get(Supplier, setup["supplier"]).is_active = False
    product = session.get(Product, setup["product"])
    product.is_active = False
    product.name = "Nume nou"
    session.commit()
    client, headers = authorize(setup["warehouse"])
    response = client.post("/api/receipts", headers=headers, json=payload(setup))
    assert response.status_code == 201
    assert response.json["receipt"]["items"][0]["description"] == "Produs comandat"


@pytest.mark.parametrize("fail_on_call", [1, 2])
def test_audit_failure_rolls_back_receipt_and_items(session, setup, fail_on_call):
    from app.services.audit import record_audit

    client, headers = authorize(setup["warehouse"])
    calls = 0

    def fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise SQLAlchemyError("test")
        return record_audit(**kwargs)

    with patch("app.services.receipts.record_audit", side_effect=fail):
        assert client.post("/api/receipts", headers=headers, json=payload(setup)).status_code == 503
    assert_empty(session)


def test_auth_errors_limits_and_pagination(session, setup):
    assert current_app.test_client().get("/api/receipts").status_code == 401
    client, headers = authorize(setup["warehouse"])
    assert client.post("/api/receipts", json=payload(setup)).status_code == 401
    assert client.post("/api/receipts", headers=headers, data="x").status_code == 415
    assert client.post("/api/receipts", headers=headers, data="{", content_type="application/json").status_code == 400
    assert client.post("/api/receipts", headers=headers, json=[]).status_code == 400
    assert client.post("/api/receipts", headers=headers, json={"x": "x" * 66000}).status_code == 413
    data = payload(setup)
    data["items"] *= 101
    assert client.post("/api/receipts", headers=headers, json=data).status_code == 400
    for missing in (999, 9223372036854775808):
        assert client.get(f"/api/receipts/{missing}").status_code == 404
    assert client.post("/api/receipts", headers=headers, json=payload(setup, purchase_order_id=999)).status_code == 404
    for query in ("page=0", "per_page=101", "page=x", "page=1&page=2", "status=DRAFT"):
        assert client.get(f"/api/receipts?{query}").status_code == 400
    assert client.get("/api/receipts").json["receipts"] == []


@pytest.mark.parametrize("inactive", [False, True])
def test_service_rechecks_actor(session, setup, inactive):
    actor = setup["warehouse"] if inactive else setup["buyer"]
    if inactive:
        session.get(User, actor).is_active = False
        session.commit()
    with pytest.raises(ReceiptCreationForbiddenError):
        create_receipt(actor_user_id=actor, **payload(setup))
    assert_empty(session)


def test_database_enforces_quantity_balance(session, setup):
    client, headers = authorize(setup["warehouse"])
    receipt = client.post("/api/receipts", headers=headers, json=payload(setup)).json["receipt"]
    item_id = receipt["items"][0]["id"]
    for value in ("NaN", "-1", "1"):
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(text("UPDATE receipt_items SET accepted_quantity = CAST(:value AS numeric) WHERE id = :id"),
                                {"value": value, "id": item_id})


def test_receipt_creation_does_not_query_prices(session, setup):
    statements = []
    connection = session.connection()

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", capture)
    try:
        create_receipt(actor_user_id=setup["warehouse"], **payload(setup))
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert statements
    assert all("unit_price" not in statement and "vat_rate" not in statement for statement in statements)


def draft(session, setup):
    client, headers = authorize(setup["warehouse"])
    response = client.post("/api/receipts", headers=headers, json=payload(setup))
    assert response.status_code == 201
    return client, headers, response.json["receipt"]


def edit_payload(receipt, **changes):
    return {"version": receipt["version"], "reason": "Corectie numarare", "delivery_reference": receipt["delivery_reference"],
            "received_at": receipt["received_at"], "items": [
                {"id": item["id"], "received_quantity": item["received_quantity"]} for item in receipt["items"]
            ], **changes}


def test_edit_receipt_header_quantity_and_audit(session, setup):
    client, headers, receipt = draft(session, setup)
    data = edit_payload(receipt, delivery_reference=" AVIZ corectat ", received_at="2026-10-20T12:00:00+03:00")
    data["items"][0]["received_quantity"] = "4.250"
    response = client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=data)
    assert response.status_code == 200
    result = response.json["receipt"]
    assert result["version"] == 2
    assert result["number"] == receipt["number"]
    assert result["created_by_id"] == receipt["created_by_id"]
    assert result["supplier_id"] == receipt["supplier_id"]
    assert result["delivery_reference"] == "AVIZ corectat"
    assert result["received_at"] == "2026-10-20T09:00:00+00:00"
    assert result["items"][0]["id"] == receipt["items"][0]["id"]
    assert result["items"][0]["pending_quantity"] == result["items"][0]["received_quantity"] == "4.250"
    assert result["items"][0]["accepted_quantity"] == result["items"][0]["rejected_quantity"] == "0.000"
    events = session.scalars(select(AuditEvent).where(AuditEvent.action == "UPDATE", AuditEvent.entity_type.in_(("receipts", "receipt_items")))
                              .order_by(AuditEvent.id)).all()
    assert len(events) == 2
    assert events[0].before_data["version"] == 1
    assert events[0].after_data["version"] == 2
    assert events[1].before_data["received_quantity"] == "3.125"
    assert events[1].after_data["received_quantity"] == "4.250"
    assert all(event.reason == data["reason"] and event.actor_user_id == setup["warehouse"] for event in events)
    assert response.headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in response.headers
    assert client.get(f"/api/receipts/{receipt['id']}").json["receipt"] == result


def test_noop_and_stale_version(session, setup):
    client, headers, receipt = draft(session, setup)
    data = edit_payload(receipt, delivery_reference=" AVIZ-123 ", received_at="2026-10-20T10:30:00+03:00")
    response = client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=data)
    assert response.status_code == 200
    assert response.json["receipt"] == receipt
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type.in_(("receipts", "receipt_items")))) == 2
    data["items"][0]["received_quantity"] = "5"
    assert client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=data).status_code == 200
    data["items"][0]["received_quantity"] = "7"
    assert client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=data).status_code == 409
    stored = client.get(f"/api/receipts/{receipt['id']}").json["receipt"]
    assert stored["items"][0]["received_quantity"] == "5.000"
    assert stored["version"] == 2


@pytest.mark.parametrize("status", ["CONFIRMED", "CANCELLED"])
def test_only_receipt_drafts_can_be_edited(session, setup, status):
    client, headers, receipt = draft(session, setup)
    session.get(Receipt, receipt["id"]).status = status
    session.commit()
    assert client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=edit_payload(receipt)).status_code == 409


@pytest.mark.parametrize("changes", [
    {"version": True}, {"version": "1"}, {"version": 0}, {"version": 2147483648},
    {"reason": " "}, {"reason": None}, {"reason": "x" * 1001},
    {"delivery_reference": " "}, {"received_at": "2026-10-20T10:30:00"},
    {"items": []}, {"items": None}, {"status": "CONFIRMED"}, {"supplier_id": 1},
])
def test_invalid_edits_leave_receipt_unchanged(session, setup, changes):
    client, headers, receipt = draft(session, setup)
    assert client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=edit_payload(receipt, **changes)).status_code == 400
    assert client.get(f"/api/receipts/{receipt['id']}").json["receipt"] == receipt


@pytest.mark.parametrize("case", ["foreign", "duplicate", "zero", "precision", "new_id", "source", "accepted"])
def test_invalid_line_edit_is_rejected(session, setup, case):
    client, headers, receipt = draft(session, setup)
    other = client.post("/api/receipts", headers=headers, json=payload(setup)).json["receipt"]
    data = edit_payload(receipt)
    if case == "foreign":
        data["items"][0]["id"] = other["items"][0]["id"]
    elif case == "duplicate":
        data["items"] *= 2
    elif case == "zero":
        data["items"][0]["received_quantity"] = "0"
    elif case == "precision":
        data["items"][0]["received_quantity"] = "1.0001"
    elif case == "new_id":
        data["items"][0]["id"] = 999
    elif case == "source":
        data["items"][0]["purchase_order_item_id"] = setup["order"]["items"][0]["id"]
    else:
        data["items"][0]["accepted_quantity"] = "1"
    assert client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=data).status_code == 400
    assert client.get(f"/api/receipts/{receipt['id']}").json["receipt"] == receipt


@pytest.mark.parametrize("fail_on_call", [1, 2])
def test_edit_audit_failure_rolls_back_quantities_and_version(session, setup, fail_on_call):
    from app.services.audit import record_audit

    client, headers, receipt = draft(session, setup)
    data = edit_payload(receipt, delivery_reference="Corectie")
    data["items"][0]["received_quantity"] = "6"
    calls = 0

    def fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise SQLAlchemyError("test")
        return record_audit(**kwargs)

    with patch("app.services.receipts.record_audit", side_effect=fail):
        assert client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=data).status_code == 503
    assert client.get(f"/api/receipts/{receipt['id']}").json["receipt"] == receipt
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type.in_(("receipts", "receipt_items")))) == 2


def test_edit_auth_body_and_missing_receipt(session, setup):
    client, headers, receipt = draft(session, setup)
    url = f"/api/receipts/{receipt['id']}"
    data = edit_payload(receipt)
    assert current_app.test_client().patch(url, json=data).status_code == 401
    assert client.patch(url, json=data).status_code == 401
    assert client.patch(url, headers=headers, data="x").status_code == 415
    assert client.patch(url, headers=headers, data="{", content_type="application/json").status_code == 400
    assert client.patch(url, headers=headers, json=[]).status_code == 400
    assert client.patch(url, headers=headers, json={"x": "x" * 66000}).status_code == 413
    for missing in (999, 9223372036854775808):
        assert client.patch(f"/api/receipts/{missing}", headers=headers, json=data).status_code == 404
    for role in (Role.ADMIN, Role.ACHIZITII, Role.CONTABILITATE):
        user = User(name="Alt rol", email=f"receipt-edit-{role.value}@example.com", role=role,
                    password_hash="unused", token_version=1, is_active=True)
        session.add(user)
        session.flush()
        user_id = user.id
        session.commit()
        other, other_headers = authorize(user_id)
        assert other.patch(url, headers=other_headers, json=data).status_code == 403


@pytest.mark.parametrize("inactive", [False, True])
def test_edit_service_rechecks_actor(session, setup, inactive):
    from app.services.receipts import ReceiptManagementForbiddenError, edit_receipt

    _, _, receipt = draft(session, setup)
    actor = setup["warehouse"] if inactive else setup["buyer"]
    if inactive:
        session.get(User, actor).is_active = False
        session.commit()
    with pytest.raises(ReceiptManagementForbiddenError):
        edit_receipt(actor_user_id=actor, receipt_id=receipt["id"], **edit_payload(receipt))


def test_classified_quantities_cannot_be_overwritten(session, setup):
    client, headers, receipt = draft(session, setup)
    item = session.get(ReceiptItem, receipt["items"][0]["id"])
    item.accepted_quantity = 1
    item.pending_quantity -= 1
    session.commit()
    assert client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=edit_payload(receipt)).status_code == 409
    assert session.get(ReceiptItem, item.id).accepted_quantity == 1


def confirm_payload(receipt, accepted="2.000", rejected="1.000", pending="0.125", **changes):
    return {"version": receipt["version"], "reason": "Verificare marfa la primire", "items": [{
        "id": item["id"], "accepted_quantity": accepted, "rejected_quantity": rejected, "pending_quantity": pending,
    } for item in receipt["items"]], **changes}


def test_confirm_receipt_adds_only_accepted_stock_and_audit(session, setup):
    client, headers, receipt = draft(session, setup)
    assert client.get("/api/stock").json["stock"][0]["quantity"] == "0.000"
    data = confirm_payload(receipt)
    response = client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers, json=data)
    assert response.status_code == 200
    result = response.json["receipt"]
    assert result["status"] == "CONFIRMED"
    assert result["version"] == 2
    assert result["confirmed_by_id"] == setup["warehouse"]
    assert result["confirmed_at"].endswith("+00:00")
    assert result["items"][0]["accepted_quantity"] == "2.000"
    assert result["items"][0]["rejected_quantity"] == "1.000"
    assert result["items"][0]["pending_quantity"] == "0.125"
    movement = session.scalar(select(StockMovement))
    assert str(movement.quantity_delta) == "2.000"
    assert movement.receipt_item_id == receipt["items"][0]["id"]
    assert movement.product_id == setup["product"]
    assert movement.created_by_id == setup["warehouse"]
    events = session.scalars(select(AuditEvent).where(AuditEvent.entity_type == "stock_movements")).all()
    assert len(events) == 1
    assert events[0].after_data["quantity_delta"] == "2.000"
    assert session.scalar(select(AuditEvent).where(AuditEvent.entity_type == "receipts", AuditEvent.action == "CONFIRM")).after_data["status"] == "CONFIRMED"
    assert client.get("/api/stock").json["stock"][0]["quantity"] == "2.000"
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers, json=data).status_code == 409
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 1
    assert client.patch(f"/api/receipts/{receipt['id']}", headers=headers, json=edit_payload(result)).status_code == 409
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("accepted,rejected,pending", [("0", "3.125", "0"), ("0", "0", "3.125")])
def test_rejected_or_pending_goods_do_not_enter_stock(session, setup, accepted, rejected, pending):
    client, headers, receipt = draft(session, setup)
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers,
                       json=confirm_payload(receipt, accepted, rejected, pending)).status_code == 200
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert client.get("/api/stock").json["stock"][0]["quantity"] == "0.000"


def test_cumulative_acceptance_cannot_exceed_ordered_quantity(session, setup):
    client, headers = authorize(setup["warehouse"])
    data = payload(setup)
    data["items"][0]["received_quantity"] = "7.000"
    first = client.post("/api/receipts", headers=headers, json=data).json["receipt"]
    second = client.post("/api/receipts", headers=headers, json=data).json["receipt"]
    assert client.post(f"/api/receipts/{first['id']}/confirm", headers=headers,
                       json=confirm_payload(first, "7", "0", "0")).status_code == 200
    assert client.post(f"/api/receipts/{second['id']}/confirm", headers=headers,
                       json=confirm_payload(second, "4", "0", "3")).status_code == 409
    assert session.get(Receipt, second["id"]).status == "DRAFT"
    assert client.post(f"/api/receipts/{second['id']}/confirm", headers=headers,
                       json=confirm_payload(second, "3", "0", "4")).status_code == 200
    assert client.get("/api/stock").json["stock"][0]["quantity"] == "10.000"


@pytest.mark.parametrize("changes", [{"version": True}, {"version": 0}, {"reason": " "}, {"reason": None},
                                     {"reason": "x" * 1001}, {"items": []}, {"items": None}, {"status": "CONFIRMED"}])
def test_invalid_confirmation_header_has_no_effect(session, setup, changes):
    client, headers, receipt = draft(session, setup)
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers,
                       json=confirm_payload(receipt, **changes)).status_code == 400
    assert client.get(f"/api/receipts/{receipt['id']}").json["receipt"] == receipt
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0


@pytest.mark.parametrize("case", ["sum", "negative", "float", "precision", "nan", "duplicate", "foreign", "received"])
def test_invalid_confirmation_lines_have_no_effect(session, setup, case):
    client, headers, receipt = draft(session, setup)
    data = confirm_payload(receipt)
    if case == "sum":
        data["items"][0]["accepted_quantity"] = "3.125"
    elif case == "negative":
        data["items"][0]["rejected_quantity"] = "-1"
    elif case == "float":
        data["items"][0]["accepted_quantity"] = 2.0
    elif case == "precision":
        data["items"][0]["pending_quantity"] = "0.1250"
    elif case == "nan":
        data["items"][0]["accepted_quantity"] = "NaN"
    elif case == "duplicate":
        data["items"] *= 2
    elif case == "foreign":
        other = client.post("/api/receipts", headers=headers, json=payload(setup)).json["receipt"]
        data["items"][0]["id"] = other["items"][0]["id"]
    else:
        data["items"][0]["received_quantity"] = "3.125"
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers, json=data).status_code == 400
    assert client.get(f"/api/receipts/{receipt['id']}").json["receipt"] == receipt
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0


@pytest.mark.parametrize("case", ["closed", "product_inactive", "unit", "supplier", "unmatched"])
def test_acceptance_requires_compatible_open_order(session, setup, case):
    client, headers, receipt = draft(session, setup)
    if case == "closed":
        session.get(PurchaseOrder, setup["order"]["id"]).status = "CLOSED"
    elif case == "product_inactive":
        session.get(Product, setup["product"]).is_active = False
    elif case == "unit":
        session.get(ReceiptItem, receipt["items"][0]["id"]).unit = "BUC"
    elif case == "supplier":
        other = Supplier(name="Alt furnizor", tax_country="RO", tax_id="999")
        session.add(other)
        session.flush()
        session.get(Receipt, receipt["id"]).supplier_id = other.id
    else:
        session.get(ReceiptItem, receipt["items"][0]["id"]).purchase_order_item_id = None
    session.commit()
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers,
                       json=confirm_payload(receipt)).status_code == (400 if case == "unmatched" else 409)
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert session.get(Receipt, receipt["id"]).status == "DRAFT"


@pytest.mark.parametrize("fail_on_call", [1, 2, 3])
def test_confirmation_audit_failure_rolls_back_stock_and_classification(session, setup, fail_on_call):
    from app.services.audit import record_audit

    client, headers, receipt = draft(session, setup)
    calls = 0

    def fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise SQLAlchemyError("test")
        return record_audit(**kwargs)

    with patch("app.services.receipts.record_audit", side_effect=fail):
        assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers, json=confirm_payload(receipt)).status_code == 503
    assert client.get(f"/api/receipts/{receipt['id']}").json["receipt"] == receipt
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "stock_movements")) == 0


def test_confirmation_auth_version_and_missing_receipt(session, setup):
    client, headers, receipt = draft(session, setup)
    url = f"/api/receipts/{receipt['id']}/confirm"
    data = confirm_payload(receipt)
    assert current_app.test_client().post(url, json=data).status_code == 401
    assert client.post(url, json=data).status_code == 401
    assert client.post(url, headers=headers, data="x").status_code == 415
    assert client.post(url, headers=headers, json=[]).status_code == 400
    assert client.post(url, headers=headers, json={"x": "x" * 66000}).status_code == 413
    for missing in (999, 9223372036854775808):
        assert client.post(f"/api/receipts/{missing}/confirm", headers=headers, json=data).status_code == 404
    updated = client.patch(f"/api/receipts/{receipt['id']}", headers=headers,
                           json=edit_payload(receipt, delivery_reference="Corectie")).json["receipt"]
    assert client.post(url, headers=headers, json=data).status_code == 409
    assert session.get(Receipt, receipt["id"]).version == updated["version"]
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    other, other_headers = authorize(setup["buyer"])
    assert other.post(url, headers=other_headers, json=data).status_code == 403


@pytest.mark.parametrize("inactive", [False, True])
def test_confirm_service_rechecks_actor(session, setup, inactive):
    from app.services.receipts import ReceiptManagementForbiddenError, confirm_receipt

    _, _, receipt = draft(session, setup)
    actor = setup["warehouse"] if inactive else setup["buyer"]
    if inactive:
        session.get(User, actor).is_active = False
        session.commit()
    with pytest.raises(ReceiptManagementForbiddenError):
        confirm_receipt(actor_user_id=actor, receipt_id=receipt["id"], **confirm_payload(receipt))


def test_stock_movement_is_immutable_and_operation_key_is_unique(session, setup):
    from sqlalchemy.exc import DBAPIError

    client, headers, receipt = draft(session, setup)
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers, json=confirm_payload(receipt)).status_code == 200
    movement = session.scalar(select(StockMovement))
    movement_id = movement.id
    for statement in ("UPDATE stock_movements SET quantity_delta = 5 WHERE id = :id", "DELETE FROM stock_movements WHERE id = :id"):
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text(statement), {"id": movement_id})
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.execute(text("INSERT INTO stock_movements (product_id, receipt_item_id, kind, quantity_delta, reason, created_by_id, operation_key) "
                                 "SELECT product_id, receipt_item_id, kind, quantity_delta, reason, created_by_id, operation_key FROM stock_movements WHERE id = :id"), {"id": movement_id})


def test_stock_roles_and_pagination(session, setup):
    assert current_app.test_client().get("/api/stock").status_code == 401
    client, _ = authorize(setup["warehouse"])
    for query in ("page=0", "per_page=101", "page=x", "page=1&page=2", "role=ADMIN"):
        assert client.get(f"/api/stock?{query}").status_code == 400
    assert client.get("/api/stock?page=2&per_page=1").json["stock"] == []
    for role in Role:
        user = User(name="Stoc test", email=f"stock-{role.value}@example.com", role=role,
                    password_hash="unused", token_version=1, is_active=True)
        session.add(user)
        session.flush()
        user_id = user.id
        session.commit()
        other, other_headers = authorize(user_id)
        response = other.get("/api/stock")
        assert response.status_code == (403 if role == Role.ADMIN else 200)
        if role != Role.DEPOZIT:
            assert other.post("/api/receipts/1/confirm", headers=other_headers, json={}).status_code == 403


def test_two_operators_cannot_accept_the_same_order_remainder(session, monkeypatch):
    import importlib.util
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    from pathlib import Path
    from threading import Barrier
    from uuid import uuid4

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.orm import scoped_session, sessionmaker
    from sqlalchemy.schema import CreateSchema, DropSchema

    from app.extensions import db
    from app.models import PurchaseOrderItem
    from app.services.receipts import ReceiptConflictError, confirm_receipt

    app = current_app._get_current_object()
    engine = db.engine
    schema = f"ruris_stock_test_{uuid4().hex}"
    scoped = scoped_session(sessionmaker(bind=engine))
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
            migrations = Path(__file__).resolve().parents[1] / "migrations" / "versions"
            with Operations.context(MigrationContext.configure(connection)):
                for path in sorted(migrations.glob("0*.py")):
                    spec = importlib.util.spec_from_file_location(f"stock_test_{path.stem}", path)
                    migration = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(migration)
                    migration.upgrade()
        scoped.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
        buyer = User(name="Achizitii", email="buyer@example.com", role=Role.ACHIZITII, password_hash="unused", token_version=1)
        operators = [User(name="Depozit", email=f"warehouse-{index}@example.com", role=Role.DEPOZIT,
                          password_hash="unused", token_version=1) for index in range(2)]
        supplier = Supplier(name="Test", tax_country="RO", tax_id="123")
        product = Product(sku="P1", name="Test", unit="KG")
        scoped.add_all([buyer, *operators, supplier, product])
        scoped.flush()
        order = PurchaseOrder(supplier_id=supplier.id, currency="RON", status="CONFIRMED", owner_id=buyer.id,
                              created_by_id=buyer.id, confirmed_at=datetime.now(timezone.utc))
        order.items.append(PurchaseOrderItem(line_number=1, product_id=product.id, description="Test", unit="KG",
                                             quantity=10, unit_price=1, vat_rate=0, expected_date=datetime.now(timezone.utc).date()))
        scoped.add(order)
        scoped.flush()
        arguments = []
        for operator in operators:
            receipt = Receipt(supplier_id=supplier.id, delivery_reference="Test", received_at=datetime.now(timezone.utc), created_by_id=operator.id)
            receipt.items.append(ReceiptItem(line_number=1, product_id=product.id, purchase_order_item_id=order.items[0].id,
                                             description="Test", unit="KG", received_quantity=7, pending_quantity=7))
            scoped.add(receipt)
            scoped.flush()
            arguments.append({"actor_user_id": operator.id, "receipt_id": receipt.id, "version": 1, "reason": "Test concurenta",
                              "items": [{"id": receipt.items[0].id, "accepted_quantity": "7", "rejected_quantity": "0", "pending_quantity": "0"}]})
        scoped.commit()
        barrier = Barrier(2)

        def worker(arguments):
            with app.app_context():
                try:
                    scoped.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
                    scoped.execute(text("SET LOCAL lock_timeout = '5s'"))
                    barrier.wait(timeout=10)
                    confirm_receipt(**arguments)
                    return "confirmed"
                except ReceiptConflictError:
                    return "conflict"
                finally:
                    scoped.remove()

        with monkeypatch.context() as patcher:
            patcher.setattr(db, "session", scoped)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(worker, arguments) for arguments in arguments]
                results = [future.result(timeout=15) for future in futures]
        assert sorted(results) == ["confirmed", "conflict"]
        scoped.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
        assert scoped.scalar(select(func.sum(StockMovement.quantity_delta))) == 7
        assert scoped.scalar(select(func.count()).select_from(Receipt).where(Receipt.status == "CONFIRMED")) == 1
        assert scoped.scalar(select(func.count()).select_from(Receipt).where(Receipt.status == "DRAFT")) == 1
        assert scoped.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "CONFIRM")) == 1
    finally:
        scoped.remove()
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))


@pytest.mark.parametrize("role", list(Role))
def test_confirmed_receipt_visibility_filters_list_detail_and_total(session, setup, role):
    warehouse, headers, hidden = draft(session, setup)
    cancelled = warehouse.post("/api/receipts", headers=headers, json=payload(setup)).json["receipt"]
    session.get(Receipt, cancelled["id"]).status = "CANCELLED"
    session.commit()
    confirmed = warehouse.post("/api/receipts", headers=headers, json=payload(setup)).json["receipt"]
    confirmed = warehouse.post(f"/api/receipts/{confirmed['id']}/confirm", headers=headers,
                               json=confirm_payload(confirmed)).json["receipt"]
    user = User(name="Cititor", email="receipt-reader@example.com", role=role,
                password_hash="unused", token_version=1, is_active=True)
    session.add(user)
    session.flush()
    user_id = user.id
    session.commit()
    client, reader_headers = authorize(user_id)
    response = client.get("/api/receipts?per_page=1")
    if role == Role.ADMIN:
        assert response.status_code == 403
        assert client.get(f"/api/receipts/{confirmed['id']}").status_code == 403
        return
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json["total"] == (3 if role == Role.DEPOZIT else 1)
    if role != Role.DEPOZIT:
        assert response.json["receipts"] == [{**{key: value for key, value in confirmed.items() if key != "items"},
                                               "supplier_name": "Furnizor", "pending_count": 1}]
        assert client.get("/api/receipts?page=2&per_page=1").json["receipts"] == []
    expected = {**confirmed, "supplier_name": "Furnizor", "items": [{**confirmed["items"][0],
        "total_accepted_quantity": "2.000", "pending_order_number": setup["order"]["number"],
        "pending_product_name": "Produs comandat", "acceptances": []}]}
    assert client.get(f"/api/receipts/{confirmed['id']}").json["receipt"] == expected
    for receipt in (hidden, cancelled):
        assert client.get(f"/api/receipts/{receipt['id']}").status_code == (200 if role == Role.DEPOZIT else 404)
    if role != Role.DEPOZIT:
        assert client.post("/api/receipts", headers=reader_headers, json=payload(setup)).status_code == 403
        assert client.patch(f"/api/receipts/{hidden['id']}", headers=reader_headers, json=edit_payload(hidden)).status_code == 403
        assert client.post(f"/api/receipts/{hidden['id']}/confirm", headers=reader_headers, json=confirm_payload(hidden)).status_code == 403
    assert client.get("/api/receipts?role=DEPOZIT").status_code == 400


@pytest.mark.parametrize("missing", ["date", "actor"])
def test_incomplete_confirmation_metadata_is_hidden_from_other_teams(session, setup, missing):
    warehouse, headers, receipt = draft(session, setup)
    result = warehouse.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers, json=confirm_payload(receipt))
    assert result.status_code == 200
    stored = session.get(Receipt, receipt["id"])
    if missing == "date":
        stored.confirmed_at = None
    else:
        stored.confirmed_by_id = None
    session.commit()
    buyer, _ = authorize(setup["buyer"])
    assert buyer.get("/api/receipts").json["total"] == 0
    assert buyer.get(f"/api/receipts/{receipt['id']}").status_code == 404


def test_cached_draft_cannot_bypass_receipt_visibility(session, setup):
    from app.services.receipts import ReceiptManagementForbiddenError, ReceiptNotFoundError, get_receipt, list_receipts

    _, _, receipt = draft(session, setup)
    cached = session.get(Receipt, receipt["id"])
    assert get_receipt(receipt["id"], role=Role.DEPOZIT)["id"] == cached.id
    with pytest.raises(ReceiptNotFoundError):
        get_receipt(receipt["id"], role=Role.CONTABILITATE)
    assert list_receipts(page=1, per_page=20, role=Role.ACHIZITII)["total"] == 0
    with pytest.raises(ReceiptManagementForbiddenError):
        get_receipt(receipt["id"], role=Role.ADMIN)
    with pytest.raises(ReceiptManagementForbiddenError):
        list_receipts(page=1, per_page=20, role=Role.ADMIN)


def test_delivery_remainder_uses_only_confirmed_accepted_quantities(session, setup):
    client, headers, receipt = draft(session, setup)
    url = f"/api/purchase-orders/{setup['order']['id']}/delivery"
    initial = client.get(url)
    assert initial.status_code == 200
    item = initial.json["delivery"]["items"][0]
    assert item["quantity"] == item["remaining_quantity"] == "10.000"
    assert item["accepted_quantity"] == "0.000"
    assert item["delivery_status"] == "NOT_RECEIVED"
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers, json=confirm_payload(receipt)).status_code == 200
    item = client.get(url).json["delivery"]["items"][0]
    assert item["accepted_quantity"] == "2.000"
    assert item["remaining_quantity"] == "8.000"
    assert item["delivery_status"] == "PARTIAL"
    data = payload(setup)
    data["items"][0]["received_quantity"] = "8.000"
    next_receipt = client.post("/api/receipts", headers=headers, json=data).json["receipt"]
    assert client.get(url).json["delivery"]["items"][0]["remaining_quantity"] == "8.000"
    assert client.post(f"/api/receipts/{next_receipt['id']}/confirm", headers=headers,
                       json=confirm_payload(next_receipt, "8", "0", "0")).status_code == 200
    item = client.get(url).json["delivery"]["items"][0]
    assert item["accepted_quantity"] == "10.000"
    assert item["remaining_quantity"] == "0.000"
    assert item["delivery_status"] == "COMPLETE"
    assert initial.headers["Cache-Control"] == "no-store"


def test_delivery_remainder_keeps_order_lines_and_other_orders_separate(session, setup):
    from app.models import PurchaseOrderItem

    order = create_order(actor_user_id=setup["buyer"], supplier_id=setup["supplier"], currency="RON", items=[{
        "product_id": setup["product"], "quantity": "5.250", "unit_price": "1", "vat_rate": "0", "expected_date": "2026-11-10",
    }, {
        "product_id": setup["product"], "quantity": "4.750", "unit_price": "1", "vat_rate": "0", "expected_date": "2026-12-10",
    }])
    order = confirm_order(actor_user_id=setup["buyer"], order_id=order["id"], version=1)
    client, headers = authorize(setup["warehouse"])
    first = client.post("/api/receipts", headers=headers, json=payload(setup)).json["receipt"]
    assert client.post(f"/api/receipts/{first['id']}/confirm", headers=headers, json=confirm_payload(first)).status_code == 200
    receipt = client.post("/api/receipts", headers=headers, json=payload(setup, purchase_order_id=order["id"], items=[{
        "purchase_order_item_id": order["items"][0]["id"], "received_quantity": "1.125",
    }])).json["receipt"]
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers,
                       json=confirm_payload(receipt, "1.125", "0", "0")).status_code == 200
    result = client.get(f"/api/purchase-orders/{order['id']}/delivery").json["delivery"]
    assert [item["accepted_quantity"] for item in result["items"]] == ["1.125", "0.000"]
    assert [item["remaining_quantity"] for item in result["items"]] == ["4.125", "4.750"]
    assert [item["delivery_status"] for item in result["items"]] == ["PARTIAL", "NOT_RECEIVED"]
    assert session.scalar(select(func.count()).select_from(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order["id"])) == 2


@pytest.mark.parametrize("role", list(Role))
def test_delivery_remainder_respects_roles_and_hides_drafts(session, setup, role):
    hidden = create_order(actor_user_id=setup["buyer"], supplier_id=setup["supplier"], currency="RON", items=[])
    user = User(name="Livrari", email="delivery-reader@example.com", role=role,
                password_hash="unused", token_version=1, is_active=True)
    session.add(user)
    session.flush()
    user_id = user.id
    session.commit()
    client, _ = authorize(user_id)
    response = client.get(f"/api/purchase-orders/{setup['order']['id']}/delivery")
    assert response.status_code == (403 if role == Role.ADMIN else 200)
    if role != Role.ADMIN:
        assert set(response.json["delivery"]) == {"id", "number", "status", "delivery_status", "items"}
        assert set(response.json["delivery"]["items"][0]) == {
            "id", "line_number", "product_id", "description", "unit", "quantity", "expected_date",
            "accepted_quantity", "remaining_quantity", "delivery_status",
        }
    assert client.get(f"/api/purchase-orders/{hidden['id']}/delivery").status_code == (
        200 if role == Role.ACHIZITII else 403 if role == Role.ADMIN else 404
    )


def test_delivery_is_read_only_and_handles_missing_orders(session, setup):
    client, _ = authorize(setup["warehouse"])
    url = f"/api/purchase-orders/{setup['order']['id']}/delivery"
    assert current_app.test_client().get(url).status_code == 401
    before_audit = session.scalar(select(func.count()).select_from(AuditEvent))
    for _ in range(2):
        assert client.get(url).status_code == 200
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before_audit
    assert session.get(PurchaseOrder, setup["order"]["id"]).version == 2
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    for missing in (999, 9223372036854775808):
        assert client.get(f"/api/purchase-orders/{missing}/delivery").status_code == 404


@pytest.fixture
def overdue_today(monkeypatch):
    from datetime import date

    monkeypatch.setattr("app.services.purchase_orders.bucharest_date", lambda: date(2026, 10, 20))


@pytest.mark.parametrize("moment,expected", [
    ("2026-01-01T21:30:00+00:00", "2026-01-01"),
    ("2026-01-01T22:30:00+00:00", "2026-01-02"),
    ("2026-07-01T21:30:00+00:00", "2026-07-02"),
])
def test_bucharest_date_handles_local_midnight_in_winter_and_summer(session, moment, expected):
    from datetime import datetime
    from app.services.purchase_orders import bucharest_date

    assert bucharest_date(datetime.fromisoformat(moment)).isoformat() == expected


@pytest.mark.parametrize("deadline,expected_count,days", [
    ("2026-10-19", 1, 1), ("2026-10-20", 0, None), ("2026-10-21", 0, None),
])
def test_overdue_starts_the_day_after_the_deadline(session, setup, overdue_today, deadline, expected_count, days):
    from datetime import date

    session.get(PurchaseOrder, setup["order"]["id"]).items[0].expected_date = date.fromisoformat(deadline)
    session.commit()
    client, _ = authorize(setup["warehouse"])
    before_audit = session.scalar(select(func.count()).select_from(AuditEvent))
    response = client.get("/api/purchase-orders/overdue")
    assert response.status_code == 200
    assert response.json["as_of"] == "2026-10-20"
    assert response.json["timezone"] == "Europe/Bucharest"
    assert response.json["total"] == expected_count
    if expected_count:
        item = response.json["items"][0]
        assert item["days_overdue"] == days
        assert item["remaining_quantity"] == "10.000"
        assert item["accepted_quantity"] == "0.000"
        assert item["order_id"] == setup["order"]["id"]
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before_audit
    assert response.headers["Cache-Control"] == "no-store"


def test_partial_delivery_stays_overdue_until_fully_accepted(session, setup, overdue_today):
    from datetime import date

    session.get(PurchaseOrder, setup["order"]["id"]).items[0].expected_date = date(2026, 10, 18)
    session.commit()
    client, headers, receipt = draft(session, setup)
    assert client.get("/api/purchase-orders/overdue").json["items"][0]["remaining_quantity"] == "10.000"
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers, json=confirm_payload(receipt)).status_code == 200
    item = client.get("/api/purchase-orders/overdue").json["items"][0]
    assert item["accepted_quantity"] == "2.000"
    assert item["remaining_quantity"] == "8.000"
    assert item["days_overdue"] == 2
    data = payload(setup)
    data["items"][0]["received_quantity"] = "8"
    last = client.post("/api/receipts", headers=headers, json=data).json["receipt"]
    assert client.post(f"/api/receipts/{last['id']}/confirm", headers=headers, json=confirm_payload(last, "8", "0", "0")).status_code == 200
    assert client.get("/api/purchase-orders/overdue").json["total"] == 0
    assert client.get(f"/api/purchase-orders/{setup['order']['id']}/delivery").json["delivery"]["items"][0]["remaining_quantity"] == "0.000"


@pytest.mark.parametrize("status", ["DRAFT", "CANCELLED", "CLOSED"])
def test_non_open_orders_are_not_overdue(session, setup, overdue_today, status):
    from datetime import date

    order = session.get(PurchaseOrder, setup["order"]["id"])
    order.status = status
    order.items[0].expected_date = date(2026, 10, 18)
    session.commit()
    client, _ = authorize(setup["buyer"])
    assert client.get("/api/purchase-orders/overdue").json["items"] == []


def test_overdue_pagination_orders_by_oldest_deadline(session, setup, overdue_today):
    from datetime import date

    session.get(PurchaseOrder, setup["order"]["id"]).items[0].expected_date = date(2026, 10, 18)
    session.commit()
    second = create_order(actor_user_id=setup["buyer"], supplier_id=setup["supplier"], currency="RON", items=[{
        "product_id": setup["product"], "quantity": "4", "unit_price": "1", "vat_rate": "0", "expected_date": "2026-10-17",
    }])
    second = confirm_order(actor_user_id=setup["buyer"], order_id=second["id"], version=1)
    client, _ = authorize(setup["buyer"])
    first_page = client.get("/api/purchase-orders/overdue?per_page=1").json
    assert first_page["total"] == 2
    assert first_page["items"][0]["order_id"] == second["id"]
    second_page = client.get("/api/purchase-orders/overdue?page=2&per_page=1").json
    assert second_page["items"][0]["order_id"] == setup["order"]["id"]
    assert client.get("/api/purchase-orders/overdue?page=3&per_page=1").json["items"] == []
    for query in ("page=0", "per_page=101", "page=x", "page=1&page=2", "as_of=2026-12-01"):
        assert client.get(f"/api/purchase-orders/overdue?{query}").status_code == 400


@pytest.mark.parametrize("role", list(Role))
def test_overdue_permissions_and_response_fields(session, setup, overdue_today, role):
    from datetime import date

    session.get(PurchaseOrder, setup["order"]["id"]).items[0].expected_date = date(2026, 10, 18)
    user = User(name="Intarzieri", email="overdue-reader@example.com", role=role,
                password_hash="unused", token_version=1, is_active=True)
    session.add(user)
    session.flush()
    user_id = user.id
    session.commit()
    client, _ = authorize(user_id)
    assert current_app.test_client().get("/api/purchase-orders/overdue").status_code == 401
    response = client.get("/api/purchase-orders/overdue")
    assert response.status_code == (403 if role == Role.ADMIN else 200)
    if role != Role.ADMIN:
        assert set(response.json["items"][0]) == {
            "order_id", "order_number", "supplier_id", "id", "line_number", "product_id", "description", "unit",
            "quantity", "expected_date", "accepted_quantity", "remaining_quantity", "days_overdue",
        }


def test_overdue_database_failure_returns_safe_error(session, setup):
    client, _ = authorize(setup["buyer"])
    with patch("app.services.purchase_orders.bucharest_date", side_effect=SQLAlchemyError("private detail")):
        response = client.get("/api/purchase-orders/overdue")
    assert response.status_code == 503
    assert "private detail" not in response.get_data(as_text=True)
