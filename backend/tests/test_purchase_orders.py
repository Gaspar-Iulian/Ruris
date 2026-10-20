from decimal import Decimal
from unittest.mock import patch

from flask import current_app
from flask_jwt_extended import create_access_token, get_csrf_token
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models import AuditEvent, Product, PurchaseOrder, PurchaseOrderItem, Role, Supplier, User
from app.services.purchase_orders import OrderCreationForbiddenError, create_order


@pytest.fixture
def setup(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    supplier = Supplier(name="Furnizor test", tax_country="RO", tax_id="123")
    product = Product(sku="P1", name="Produs initial", unit="KG")
    session.add_all([supplier, product])
    session.flush()
    values = {"supplier_id": supplier.id, "product_id": product.id}
    session.commit()
    return values


def authorize(session, role=Role.ACHIZITII):
    user = User(name="Test", email=f"orders-{role.value}@example.com", role=role,
                password_hash="unused", token_version=1, is_active=True)
    session.add(user)
    session.flush()
    actor = user.id
    session.commit()
    token = create_access_token(identity=str(actor), additional_claims={"token_version": 1})
    client = current_app.test_client()
    client.set_cookie("access_token_cookie", token, path="/api")
    return client, {"X-CSRF-TOKEN": get_csrf_token(token)}, actor


def payload(setup, **changes):
    return {"supplier_id": setup["supplier_id"], "currency": "RON", "items": [{
        "product_id": setup["product_id"], "quantity": "2.125", "unit_price": "10.1234",
        "vat_rate": "19.00", "expected_date": "2026-11-10",
    }], **changes}


def assert_empty(session):
    for model in (PurchaseOrder, PurchaseOrderItem, AuditEvent):
        assert session.scalar(select(func.count()).select_from(model)) == 0


def test_create_draft_with_exact_decimals_and_complete_audit(session, setup):
    client, headers, actor = authorize(session)
    response = client.post("/api/purchase-orders", headers=headers, json=payload(setup))
    assert response.status_code == 201
    order = response.json["order"]
    assert order["number"] == f"CA-{order['id']}"
    assert order["status"] == "DRAFT"
    assert order["version"] == 1
    assert order["owner_id"] == order["created_by_id"] == actor
    item = order["items"][0]
    assert item["quantity"] == "2.125"
    assert item["unit_price"] == "10.1234"
    assert item["description"] == "Produs initial"
    assert item["unit"] == "KG"
    assert session.get(PurchaseOrderItem, item["id"]).unit_price == Decimal("10.1234")
    events = session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    assert len(events) == 2
    assert events[0].entity_type == "purchase_orders"
    assert events[0].after_data == {key: value for key, value in order.items() if key not in {"id", "items"}}
    assert events[1].entity_id == item["id"]
    assert events[1].after_data == {"purchase_order_id": order["id"], **{key: value for key, value in item.items() if key != "id"}}
    assert all(event.actor_user_id == actor for event in events)
    assert response.headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in response.headers
    assert client.get(f"/api/purchase-orders/{order['id']}").json["order"] == order
    product = session.get(Product, setup["product_id"])
    product.name = "Nume nou"
    session.commit()
    assert client.get(f"/api/purchase-orders/{order['id']}").json["order"]["items"][0]["description"] == "Produs initial"


def test_empty_draft_and_separate_lines_for_same_product(session, setup):
    client, headers, _ = authorize(session)
    empty = client.post("/api/purchase-orders", headers=headers, json=payload(setup, items=[], currency="EUR"))
    assert empty.status_code == 201
    assert empty.json["order"]["items"] == []
    data = payload(setup)
    data["items"].append({**data["items"][0], "quantity": "1", "expected_date": "2026-12-01"})
    response = client.post("/api/purchase-orders", headers=headers, json=data)
    assert response.status_code == 201
    assert [item["line_number"] for item in response.json["order"]["items"]] == [1, 2]
    assert response.json["order"]["number"] != empty.json["order"]["number"]


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DEPOZIT, Role.CONTABILITATE])
def test_drafts_are_only_visible_to_purchasing(session, setup, role):
    client, headers, _ = authorize(session, role)
    assert client.post("/api/purchase-orders", headers=headers, json=payload(setup)).status_code == 403
    listing = client.get("/api/purchase-orders")
    assert listing.status_code == (403 if role == Role.ADMIN else 200)
    if role != Role.ADMIN:
        assert listing.json["orders"] == []
        assert listing.json["total"] == 0
    assert client.get("/api/purchase-orders/1").status_code == (403 if role == Role.ADMIN else 404)
    assert_empty(session)


@pytest.mark.parametrize("field,value", [
    ("quantity", "0"), ("quantity", "-1"), ("quantity", "1.0001"),
    ("quantity", "1000000000000000"), ("quantity", True),
    ("unit_price", 1.2), ("unit_price", "NaN"), ("unit_price", "Infinity"),
    ("unit_price", "1e2"), ("unit_price", "1,20"), ("unit_price", "1.00001"),
    ("unit_price", "100000000000000"), ("vat_rate", "100.01"), ("vat_rate", "1.001"),
    ("product_id", True), ("product_id", "1"), ("product_id", 9223372036854775808),
    ("expected_date", "2026-02-30"), ("expected_date", "20261110"), ("expected_date", None),
    ("unit", "KG"),
])
def test_invalid_line_is_rejected_without_partial_data(session, setup, field, value):
    client, headers, _ = authorize(session)
    data = payload(setup)
    data["items"][0][field] = value
    assert client.post("/api/purchase-orders", headers=headers, json=data).status_code == 400
    assert_empty(session)


@pytest.mark.parametrize("changes", [
    {"currency": "USD"}, {"currency": None}, {"supplier_id": False},
    {"supplier_id": 999}, {"items": None}, {"items": {}}, {"items": [None]},
    {"status": "CONFIRMED"}, {"owner_id": 1},
])
def test_invalid_header_is_rejected(session, setup, changes):
    client, headers, _ = authorize(session)
    assert client.post("/api/purchase-orders", headers=headers, json=payload(setup, **changes)).status_code == 400
    assert_empty(session)


@pytest.mark.parametrize("which", ["supplier", "product", "missing_product"])
def test_catalog_entries_must_exist_and_be_active(session, setup, which):
    client, headers, _ = authorize(session)
    data = payload(setup)
    if which == "missing_product":
        data["items"][0]["product_id"] = 999
    else:
        model, key = (Supplier, "supplier_id") if which == "supplier" else (Product, "product_id")
        session.get(model, setup[key]).is_active = False
        session.commit()
    assert client.post("/api/purchase-orders", headers=headers, json=data).status_code == 400
    assert_empty(session)


@pytest.mark.parametrize("fail_on_call", [1, 2])
def test_audit_failure_rolls_back_header_lines_and_audit(session, setup, fail_on_call):
    from app.services.audit import record_audit

    client, headers, _ = authorize(session)
    calls = 0

    def fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise SQLAlchemyError("test")
        return record_audit(**kwargs)

    with patch("app.services.purchase_orders.record_audit", side_effect=fail):
        assert client.post("/api/purchase-orders", headers=headers, json=payload(setup)).status_code == 503
    assert_empty(session)


def test_auth_pagination_and_body_limits(session, setup):
    client = current_app.test_client()
    assert client.get("/api/purchase-orders").status_code == 401
    client, headers, _ = authorize(session)
    assert client.post("/api/purchase-orders", json=payload(setup)).status_code == 401
    assert client.post("/api/purchase-orders", headers=headers, data="x").status_code == 415
    assert client.post("/api/purchase-orders", headers=headers, data="{", content_type="application/json").status_code == 400
    assert client.post("/api/purchase-orders", headers=headers, json=[]).status_code == 400
    assert client.post("/api/purchase-orders", headers=headers, json={"x": "x" * 66000}).status_code == 413
    data = payload(setup)
    data["items"] *= 101
    assert client.post("/api/purchase-orders", headers=headers, json=data).status_code == 400
    assert client.post("/api/purchase-orders", headers=headers, json=payload(setup)).status_code == 201
    listing = client.get("/api/purchase-orders?per_page=1").json
    assert listing["total"] == 1
    assert "items" not in listing["orders"][0]
    assert client.get("/api/purchase-orders?page=2&per_page=1").json["orders"] == []
    for query in ("page=0", "per_page=101", "page=x", "page=1&page=2", "status=DRAFT"):
        assert client.get(f"/api/purchase-orders?{query}").status_code == 400
    for missing in (999, 9223372036854775808):
        assert client.get(f"/api/purchase-orders/{missing}").status_code == 404


def test_service_rechecks_actor(session, setup):
    _, _, actor = authorize(session, Role.DEPOZIT)
    with pytest.raises(OrderCreationForbiddenError):
        create_order(actor_user_id=actor, **payload(setup))
    assert_empty(session)


def test_database_rejects_nan_and_zero_quantity(session, setup):
    client, headers, _ = authorize(session)
    response = client.post("/api/purchase-orders", headers=headers, json=payload(setup))
    item_id = response.json["order"]["items"][0]["id"]
    for value in ("NaN", "0", "-1"):
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(text("UPDATE purchase_order_items SET quantity = CAST(:value AS numeric) WHERE id = :id"),
                                {"value": value, "id": item_id})


def edit_payload(order, **changes):
    return {"supplier_id": order["supplier_id"], "currency": order["currency"], "version": order["version"],
            "reason": "Actualizare ciorna", "items": [
                {key: value for key, value in item.items() if key in {
                    "id", "product_id", "quantity", "unit_price", "vat_rate", "expected_date",
                }} for item in order["items"]
            ], **changes}


def draft(session, setup):
    client, headers, actor = authorize(session)
    response = client.post("/api/purchase-orders", headers=headers, json=payload(setup))
    assert response.status_code == 201
    return client, headers, actor, response.json["order"]


def test_edit_header_and_line_preserves_ids_and_snapshots(session, setup):
    client, headers, actor, order = draft(session, setup)
    product = session.get(Product, setup["product_id"])
    product.name = "Nume catalog nou"
    supplier = Supplier(name="Alt furnizor", tax_country="RO", tax_id="456")
    session.add(supplier)
    session.flush()
    supplier_id = supplier.id
    session.commit()
    data = edit_payload(order, currency="EUR", supplier_id=supplier_id)
    data["items"][0].update(quantity="5.500", unit_price="8.0000", expected_date="2026-12-10")
    response = client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=data)
    assert response.status_code == 200
    result = response.json["order"]
    assert result["version"] == 2
    assert result["number"] == order["number"]
    assert result["owner_id"] == result["created_by_id"] == actor
    assert result["supplier_id"] == supplier_id
    assert result["currency"] == "EUR"
    assert result["items"][0]["id"] == order["items"][0]["id"]
    assert result["items"][0]["description"] == "Produs initial"
    assert result["items"][0]["quantity"] == "5.500"
    events = session.scalars(select(AuditEvent).where(AuditEvent.action == "UPDATE").order_by(AuditEvent.id)).all()
    assert len(events) == 2
    assert events[0].before_data["version"] == 1
    assert events[0].after_data["version"] == 2
    assert events[1].before_data["quantity"] == "2.125"
    assert events[1].after_data["quantity"] == "5.500"
    assert all(event.reason == data["reason"] for event in events)
    assert response.headers["Cache-Control"] == "no-store"


def test_add_reorder_and_remove_lines_with_audit(session, setup):
    client, headers, _, order = draft(session, setup)
    data = edit_payload(order)
    new_item = {key: value for key, value in data["items"][0].items() if key != "id"}
    data["items"].insert(0, {**new_item, "quantity": "1.000"})
    result = client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=data)
    assert result.status_code == 200
    order2 = result.json["order"]
    assert order2["items"][1]["id"] == order["items"][0]["id"]
    assert [item["line_number"] for item in order2["items"]] == [1, 2]
    data = edit_payload(order2)
    data["items"].reverse()
    response = client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=data)
    assert response.status_code == 200
    order3 = response.json["order"]
    assert [item["id"] for item in order3["items"]] == [item["id"] for item in reversed(order2["items"])]
    response = client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=edit_payload(order3, items=[]))
    assert response.status_code == 200
    assert response.json["order"]["items"] == []
    assert session.scalar(select(func.count()).select_from(PurchaseOrderItem)) == 0
    deleted = session.scalars(select(AuditEvent).where(AuditEvent.action == "DELETE")).all()
    assert len(deleted) == 2
    assert {event.before_data["purchase_order_id"] for event in deleted} == {order["id"]}
    assert all(event.after_data is None for event in deleted)


def test_noop_and_stale_version(session, setup):
    client, headers, _, order = draft(session, setup)
    data = edit_payload(order)
    data["items"][0]["quantity"] = "2.125"
    response = client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=data)
    assert response.status_code == 200
    assert response.json["order"] == order
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2
    data["currency"] = "EUR"
    assert client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=data).status_code == 200
    assert client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=data).status_code == 409
    assert client.get(f"/api/purchase-orders/{order['id']}").json["order"]["version"] == 2


@pytest.mark.parametrize("status", ["CONFIRMED", "CANCELLED", "CLOSED"])
def test_only_drafts_can_be_edited(session, setup, status):
    client, headers, _, order = draft(session, setup)
    session.get(PurchaseOrder, order["id"]).status = status
    session.commit()
    assert client.patch(f"/api/purchase-orders/{order['id']}", headers=headers,
                        json=edit_payload(order, currency="EUR")).status_code == 409
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


@pytest.mark.parametrize("changes", [
    {"version": True}, {"version": "1"}, {"version": 0}, {"version": 2147483648},
    {"reason": " "}, {"reason": None}, {"reason": "x" * 1001}, {"currency": "USD"},
    {"supplier_id": 999}, {"items": None}, {"status": "CONFIRMED"},
])
def test_invalid_edits_leave_document_unchanged(session, setup, changes):
    client, headers, _, order = draft(session, setup)
    assert client.patch(f"/api/purchase-orders/{order['id']}", headers=headers,
                        json=edit_payload(order, **changes)).status_code == 400
    assert client.get(f"/api/purchase-orders/{order['id']}").json["order"] == order
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


@pytest.mark.parametrize("case", ["foreign", "duplicate", "different_product", "invalid_quantity"])
def test_invalid_line_identity_or_values(session, setup, case):
    client, headers, _, order = draft(session, setup)
    other = client.post("/api/purchase-orders", headers=headers, json=payload(setup)).json["order"]
    data = edit_payload(order)
    if case == "foreign":
        data["items"][0]["id"] = other["items"][0]["id"]
    elif case == "duplicate":
        data["items"] *= 2
    elif case == "different_product":
        data["items"][0]["product_id"] = 999
    else:
        data["items"][0]["quantity"] = "0"
    assert client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=data).status_code == 400
    assert client.get(f"/api/purchase-orders/{order['id']}").json["order"] == order


@pytest.mark.parametrize("fail_on_call", [1, 2, 3])
def test_edit_audit_failure_rolls_back_all_changes(session, setup, fail_on_call):
    from app.services.audit import record_audit

    client, headers, _, order = draft(session, setup)
    data = edit_payload(order, currency="EUR")
    data["items"] = [{key: value for key, value in data["items"][0].items() if key != "id"}]
    calls = 0

    def fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise SQLAlchemyError("test")
        return record_audit(**kwargs)

    with patch("app.services.purchase_orders.record_audit", side_effect=fail):
        assert client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=data).status_code == 503
    assert client.get(f"/api/purchase-orders/{order['id']}").json["order"] == order
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


def test_edit_auth_and_not_found(session, setup):
    client, headers, _, order = draft(session, setup)
    url = f"/api/purchase-orders/{order['id']}"
    data = edit_payload(order)
    assert current_app.test_client().patch(url, json=data).status_code == 401
    assert client.patch(url, json=data).status_code == 401
    assert client.patch(url, headers=headers, data="x").status_code == 415
    assert client.patch(url, headers=headers, json=[]).status_code == 400
    assert client.patch(url, headers=headers, json={"x": "x" * 66000}).status_code == 413
    for missing in (999, 9223372036854775808):
        assert client.patch(f"/api/purchase-orders/{missing}", headers=headers, json=data).status_code == 404
    for role in (Role.ADMIN, Role.DEPOZIT, Role.CONTABILITATE):
        other, other_headers, _ = authorize(session, role)
        assert other.patch(url, headers=other_headers, json=data).status_code == 403


def test_edit_service_rechecks_actor(session, setup):
    from app.services.purchase_orders import OrderManagementForbiddenError, edit_order

    _, _, _, order = draft(session, setup)
    _, _, actor = authorize(session, Role.DEPOZIT)
    with pytest.raises(OrderManagementForbiddenError):
        edit_order(actor_user_id=actor, order_id=order["id"], **edit_payload(order))


def test_confirm_changes_state_version_date_and_audit(session, setup):
    from datetime import datetime

    client, headers, actor, order = draft(session, setup)
    response = client.post(f"/api/purchase-orders/{order['id']}/confirm", headers=headers, json={"version": 1})
    assert response.status_code == 200
    result = response.json["order"]
    assert result["status"] == "CONFIRMED"
    assert result["version"] == 2
    assert datetime.fromisoformat(result["confirmed_at"]).utcoffset().total_seconds() == 0
    assert result["items"] == order["items"]
    assert result["number"] == order["number"]
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "CONFIRM"))
    assert event.actor_user_id == actor
    assert event.entity_id == order["id"]
    assert event.before_data["status"] == "DRAFT"
    assert event.before_data["confirmed_at"] is None
    assert event.after_data["status"] == "CONFIRMED"
    assert event.after_data["confirmed_at"] == result["confirmed_at"]
    assert response.headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in response.headers
    assert client.post(f"/api/purchase-orders/{order['id']}/confirm", headers=headers, json={"version": 2}).status_code == 409
    assert client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=edit_payload(result, currency="EUR")).status_code == 409
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "CONFIRM")) == 1


@pytest.mark.parametrize("case", ["empty", "inactive_supplier", "inactive_product", "unit_mismatch"])
def test_confirmation_revalidates_required_data(session, setup, case):
    client, headers, _, order = draft(session, setup)
    if case == "empty":
        order = client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=edit_payload(order, items=[])).json["order"]
    elif case == "inactive_supplier":
        session.get(Supplier, setup["supplier_id"]).is_active = False
    elif case == "inactive_product":
        session.get(Product, setup["product_id"]).is_active = False
    else:
        session.get(PurchaseOrderItem, order["items"][0]["id"]).unit = "BUC"
    session.commit()
    response = client.post(f"/api/purchase-orders/{order['id']}/confirm", headers=headers, json={"version": order["version"]})
    assert response.status_code == 400
    stored = session.get(PurchaseOrder, order["id"])
    assert stored.status == "DRAFT"
    assert stored.confirmed_at is None
    assert stored.version == order["version"]
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "CONFIRM")) == 0


def test_stale_version_cannot_confirm_updated_order(session, setup):
    client, headers, _, order = draft(session, setup)
    assert client.patch(f"/api/purchase-orders/{order['id']}", headers=headers, json=edit_payload(order, currency="EUR")).status_code == 200
    assert client.post(f"/api/purchase-orders/{order['id']}/confirm", headers=headers, json={"version": 1}).status_code == 409
    assert session.get(PurchaseOrder, order["id"]).status == "DRAFT"


@pytest.mark.parametrize("status", ["CANCELLED", "CLOSED"])
def test_other_states_cannot_be_confirmed(session, setup, status):
    client, headers, _, order = draft(session, setup)
    session.get(PurchaseOrder, order["id"]).status = status
    session.commit()
    assert client.post(f"/api/purchase-orders/{order['id']}/confirm", headers=headers, json={"version": 1}).status_code == 409


def test_confirm_audit_failure_rolls_back_state_and_visibility(session, setup):
    client, headers, _, order = draft(session, setup)
    warehouse, _, _ = authorize(session, Role.DEPOZIT)
    with patch("app.services.purchase_orders.record_audit", side_effect=SQLAlchemyError("test")):
        assert client.post(f"/api/purchase-orders/{order['id']}/confirm", headers=headers, json={"version": 1}).status_code == 503
    assert client.get(f"/api/purchase-orders/{order['id']}").json["order"] == order
    assert warehouse.get("/api/purchase-orders").json["total"] == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


@pytest.mark.parametrize("role", [Role.DEPOZIT, Role.CONTABILITATE])
def test_confirmed_visibility_and_role_specific_fields(session, setup, role):
    client, headers, _, order = draft(session, setup)
    hidden = client.post("/api/purchase-orders", headers=headers, json=payload(setup)).json["order"]
    assert client.post(f"/api/purchase-orders/{order['id']}/confirm", headers=headers, json={"version": 1}).status_code == 200
    other, _, _ = authorize(session, role)
    listing = other.get("/api/purchase-orders?per_page=1").json
    assert listing["total"] == 1
    assert [row["id"] for row in listing["orders"]] == [order["id"]]
    assert other.get("/api/purchase-orders?page=2&per_page=1").json["orders"] == []
    assert other.get(f"/api/purchase-orders/{hidden['id']}").status_code == 404
    response = other.get(f"/api/purchase-orders/{order['id']}")
    assert response.status_code == 200
    result = response.json["order"]
    expected_header = {"id", "number", "supplier_id", "status", "version", "confirmed_at", "items"}
    expected_item = {"id", "line_number", "product_id", "description", "unit", "quantity", "expected_date"}
    if role == Role.CONTABILITATE:
        expected_header |= {"currency", "owner_id", "created_by_id"}
        expected_item |= {"unit_price", "vat_rate"}
    assert set(result) == expected_header
    assert set(result["items"][0]) == expected_item
    assert response.headers["Cache-Control"] == "no-store"
    session.get(Supplier, setup["supplier_id"]).is_active = False
    session.get(Product, setup["product_id"]).is_active = False
    session.commit()
    assert other.get(f"/api/purchase-orders/{order['id']}").status_code == 200


def test_warehouse_query_does_not_select_prices(session, setup):
    from sqlalchemy import event
    from app.services.purchase_orders import get_order

    client, headers, _, order = draft(session, setup)
    assert client.post(f"/api/purchase-orders/{order['id']}/confirm", headers=headers, json={"version": 1}).status_code == 200
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = session.connection()
    event.listen(connection, "before_cursor_execute", capture)
    try:
        get_order(order["id"], role=Role.DEPOZIT)
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert statements
    assert all("unit_price" not in statement and "vat_rate" not in statement for statement in statements)


@pytest.mark.parametrize("data", [{}, [], {"version": True}, {"version": "1"}, {"version": 0},
                                  {"version": 2147483648}, {"version": 1, "status": "CONFIRMED"}])
def test_confirmation_rejects_invalid_body(session, setup, data):
    client, headers, _, order = draft(session, setup)
    assert client.post(f"/api/purchase-orders/{order['id']}/confirm", headers=headers, json=data).status_code == 400
    assert session.get(PurchaseOrder, order["id"]).status == "DRAFT"


def test_confirmation_auth_and_errors(session, setup):
    client, headers, _, order = draft(session, setup)
    url = f"/api/purchase-orders/{order['id']}/confirm"
    assert current_app.test_client().post(url, json={"version": 1}).status_code == 401
    assert client.post(url, json={"version": 1}).status_code == 401
    assert client.post(url, headers=headers, data="x").status_code == 415
    assert client.post(url, headers=headers, data="{", content_type="application/json").status_code == 400
    assert client.post(url, headers=headers, json={"x": "x" * 5000}).status_code == 413
    for missing in (999, 9223372036854775808):
        assert client.post(f"/api/purchase-orders/{missing}/confirm", headers=headers, json={"version": 1}).status_code == 404
    for role in (Role.ADMIN, Role.DEPOZIT, Role.CONTABILITATE):
        other, other_headers, _ = authorize(session, role)
        assert other.post(url, headers=other_headers, json={"version": 1}).status_code == 403


@pytest.mark.parametrize("inactive", [False, True])
def test_confirm_service_rechecks_actor(session, setup, inactive):
    from app.services.purchase_orders import OrderManagementForbiddenError, confirm_order

    _, _, actor, order = draft(session, setup)
    user = session.get(User, actor)
    if inactive:
        user.is_active = False
    else:
        user.role = Role.DEPOZIT
    session.commit()
    with pytest.raises(OrderManagementForbiddenError):
        confirm_order(actor_user_id=actor, order_id=order["id"], version=1)
    assert session.get(PurchaseOrder, order["id"]).status == "DRAFT"
