from unittest.mock import patch

from flask import current_app
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models import AuditEvent, Product, PurchaseOrder, Receipt, ReceiptItem, Role, StockMovement, Supplier, User
from app.services.invoices import create_invoice
from app.services.purchase_orders import confirm_order, create_order
from app.services.receipts import confirm_receipt, create_receipt
from test_invoice_allocations import authorize


def seed_exceptions(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    users = {role: User(name=role.value, email=f"pending-{role.value}@example.com", role=role,
                       password_hash="unused", token_version=1, is_active=True) for role in Role}
    supplier = Supplier(name="Furnizor clarificari", tax_country="RO", tax_id="PENDING")
    product = Product(sku="PENDING-1", name="Produs identificat", unit="BUC")
    session.add_all([*users.values(), supplier, product])
    session.flush()
    result = {"users": {role: user.id for role, user in users.items()}, "supplier_id": supplier.id, "product_id": product.id}
    session.commit()
    result["order"] = new_order(result)
    return result


@pytest.fixture
def data(session):
    return seed_exceptions(session)


def new_order(data, quantity="10"):
    order = create_order(actor_user_id=data["users"][Role.ACHIZITII], supplier_id=data["supplier_id"], currency="RON", items=[{
        "product_id": data["product_id"], "quantity": quantity, "unit_price": "2", "vat_rate": "0", "expected_date": "2026-10-20"}])
    return confirm_order(actor_user_id=data["users"][Role.ACHIZITII], order_id=order["id"], version=1)


def arrival(data, *, unknown=False, confirmed=True):
    client, headers = authorize(data["users"][Role.DEPOZIT])
    response = client.post("/api/receipts/unordered", headers=headers, json={
        "supplier_id": data["supplier_id"], "delivery_reference": "AV-FARA-COMANDA", "received_at": "2026-10-21T08:00:00Z",
        "items": [{"product_id": None if unknown else data["product_id"], "description": "Marfa sosita",
                   "unit": "BUC", "received_quantity": "10"}]})
    assert response.status_code == 201, response.json
    receipt = response.json["receipt"]
    if confirmed:
        response = client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers, json={
            "version": 1, "reason": "Sosire constatata", "items": [{"id": receipt["items"][0]["id"],
                "accepted_quantity": "0", "rejected_quantity": "0", "pending_quantity": "10"}]})
        assert response.status_code == 200, response.json
        receipt = response.json["receipt"]
    return receipt


def operation(data, receipt, kind, **changes):
    role = Role.ACHIZITII if kind == "clarify" else Role.DEPOZIT
    client, headers = authorize(data["users"][role])
    body = {"version": receipt["version"], "reason": "Decizie documentata"}
    body.update({"purchase_order_item_id": data["order"]["items"][0]["id"]} if kind == "clarify" else {"action": "ACCEPT", "quantity": "6"})
    return client.post(f"/api/receipts/{receipt['id']}/items/{receipt['items'][0]['id']}/{kind}", headers=headers, json={**body, **changes})


def test_unordered_and_unknown_goods_are_pending_without_stock(session, data):
    receipt = arrival(data, unknown=True)
    client, _ = authorize(data["users"][Role.ACHIZITII])
    assert client.get("/api/receipts/pending").json["total"] == 1
    detail = client.get(f"/api/receipts/{receipt['id']}").json["receipt"]
    assert detail["items"][0]["product_id"] is None
    assert detail["items"][0]["pending_quantity"] == "10.000"
    assert detail["items"][0]["total_accepted_quantity"] == "0.000"
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert operation(data, receipt, "resolve").status_code == 409


def test_partial_accept_then_reject_keeps_physical_arrival_and_sources(session, data):
    receipt = arrival(data, unknown=True)
    receipt = operation(data, receipt, "clarify").json["receipt"]
    assert receipt["items"][0]["pending_product_name"] == "Produs identificat"
    result = operation(data, receipt, "resolve")
    assert result.status_code == 200, result.json
    receipt = result.json["receipt"]
    item = receipt["items"][0]
    assert item["received_quantity"] == "10.000"
    assert item["pending_quantity"] == "4.000"
    assert item["total_accepted_quantity"] == "6.000"
    assert item["accepted_quantity"] == "0.000"
    assert item["acceptances"][0]["purchase_order_item_id"] == data["order"]["items"][0]["id"]
    receipt = operation(data, receipt, "resolve", action="REJECT", quantity="4").json["receipt"]
    assert receipt["items"][0]["rejected_quantity"] == "4.000"
    assert receipt["items"][0]["pending_quantity"] == "0.000"
    client, _ = authorize(data["users"][Role.DEPOZIT])
    assert client.get("/api/stock").json["stock"][0]["quantity"] == "6.000"
    assert client.get("/api/receipts/pending").json["total"] == 0
    delivery = client.get(f"/api/purchase-orders/{data['order']['id']}/delivery").json["delivery"]
    assert delivery["items"][0]["accepted_quantity"] == "6.000"
    assert delivery["items"][0]["remaining_quantity"] == "4.000"


def test_surplus_uses_supplementary_order_without_changing_initial_acceptance(session, data):
    receipt = create_receipt(actor_user_id=data["users"][Role.DEPOZIT], purchase_order_id=data["order"]["id"],
        delivery_reference="SURPLUS", received_at="2026-10-21T08:00:00Z", items=[{
            "purchase_order_item_id": data["order"]["items"][0]["id"], "received_quantity": "14"}])
    receipt = confirm_receipt(actor_user_id=data["users"][Role.DEPOZIT], receipt_id=receipt["id"], version=1, reason="Numarare", items=[{
        "id": receipt["items"][0]["id"], "accepted_quantity": "10", "rejected_quantity": "0", "pending_quantity": "4"}])
    assert operation(data, receipt, "resolve", quantity="1").status_code == 409
    second = new_order(data, "4")
    linked = operation(data, receipt, "clarify", purchase_order_item_id=second["items"][0]["id"])
    assert linked.status_code == 200
    receipt = operation(data, linked.json["receipt"], "resolve", quantity="4").json["receipt"]
    item = receipt["items"][0]
    assert item["purchase_order_item_id"] == data["order"]["items"][0]["id"]
    assert item["accepted_quantity"] == "10.000"
    assert item["received_quantity"] == item["total_accepted_quantity"] == "14.000"
    assert item["acceptances"][0]["purchase_order_item_id"] == second["items"][0]["id"]
    client, _ = authorize(data["users"][Role.DEPOZIT])
    assert client.get("/api/stock").json["stock"][0]["quantity"] == "14.000"
    for order in (data["order"], second):
        assert client.get(f"/api/purchase-orders/{order['id']}/delivery").json["delivery"]["delivery_status"] == "COMPLETE"


def test_blocked_invoice_becomes_verifiable_only_after_acceptance_and_allocation(session, data):
    receipt = arrival(data)
    invoice = create_invoice(actor_user_id=data["users"][Role.CONTABILITATE], supplier_id=data["supplier_id"], series="", number="PENDING",
        invoice_date="2026-10-21", due_date="2026-11-21", currency="RON", items=[{
            "product_id": data["product_id"], "purchase_order_item_id": data["order"]["items"][0]["id"],
            "quantity": "6", "unit_price": "2", "vat_rate": "0"}])
    client, headers = authorize(data["users"][Role.CONTABILITATE])
    url = f"/api/invoices/{invoice['id']}"
    assert client.post(url + "/verify", headers=headers, json={"version": 1}).json["invoice"]["status"] == "BLOCKED"
    assert client.get(url + "/matching").json["items"][0]["candidates"] == []
    receipt = operation(data, receipt, "clarify").json["receipt"]
    receipt = operation(data, receipt, "resolve").json["receipt"]
    assert client.get(url).json["invoice"]["status"] == "BLOCKED"
    candidate = client.get(url + "/matching").json["items"][0]["candidates"][0]
    assert candidate["available_quantity"] == "6.000"
    allocation = client.post(url + "/allocations", headers=headers, json={"version": 2, "reason": "Documente complete", "items": [{
        "invoice_item_id": invoice["items"][0]["id"], "receipt_item_id": candidate["receipt_item_id"], "quantity": "6"}]})
    assert allocation.status_code == 201, allocation.json
    assert client.post(url + "/verify", headers=headers, json={"version": 3}).json["invoice"]["status"] == "VERIFIED"


@pytest.mark.parametrize("changes", [{"quantity": "0"}, {"quantity": "NaN"}, {"quantity": "-1"}, {"quantity": 1},
                                     {"quantity": "1.0001"}, {"reason": " "}, {"version": True}, {"action": "OTHER"}])
def test_invalid_decisions_do_not_write(session, data, changes):
    receipt = arrival(data)
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    assert operation(data, receipt, "resolve", **changes).status_code == 400
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
    assert session.scalar(select(ReceiptItem.pending_quantity)) == 10


def test_limits_repeated_decisions_and_audit_rollback(session, data):
    receipt = arrival(data)
    receipt = operation(data, receipt, "clarify").json["receipt"]
    data["small_order"] = new_order(data, "2")
    receipt = operation(data, receipt, "clarify", purchase_order_item_id=data["small_order"]["items"][0]["id"]).json["receipt"]
    for quantity in ("11", "3"):
        assert operation(data, receipt, "resolve", quantity=quantity).status_code == 409
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    with patch("app.services.receipt_exceptions.record_audit", side_effect=SQLAlchemyError("test")):
        assert operation(data, receipt, "resolve", quantity="2").status_code == 503
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert session.scalar(select(func.count()).select_from(ReceiptItem)) == 1
    result = operation(data, receipt, "resolve", quantity="2")
    assert result.status_code == 200, result.json
    assert operation(data, receipt, "resolve", quantity="2").status_code == 409
    assert session.scalar(select(func.sum(StockMovement.quantity_delta))) == 2


@pytest.mark.parametrize("case", ["supplier", "unit", "product", "inactive", "closed", "draft"])
def test_incompatible_clarification_is_refused(session, data, case):
    receipt = arrival(data)
    if case == "supplier":
        other = Supplier(name="Alt furnizor", tax_country="RO", tax_id="OTHER")
        session.add(other)
        session.flush()
        session.get(PurchaseOrder, data["order"]["id"]).supplier_id = other.id
    elif case in ("closed", "draft"):
        session.get(PurchaseOrder, data["order"]["id"]).status = case.upper()
    elif case == "unit":
        session.get(ReceiptItem, receipt["items"][0]["id"]).unit = "KG"
    elif case == "inactive":
        session.get(Product, data["product_id"]).is_active = False
    else:
        other = Product(sku="OTHER", name="Alt produs", unit="BUC")
        session.add(other)
        session.flush()
        session.get(ReceiptItem, receipt["items"][0]["id"]).product_id = other.id
    session.commit()
    assert operation(data, receipt, "clarify").status_code == 409
    assert session.get(Receipt, receipt["id"]).version == 2


@pytest.mark.parametrize("role", list(Role))
def test_permissions_history_and_pending_visibility(session, data, role):
    draft = arrival(data, confirmed=False)
    receipt = arrival(data)
    client, headers = authorize(data["users"][role])
    url = f"/api/receipts/{receipt['id']}"
    assert client.get("/api/receipts/pending").status_code == (403 if role == Role.ADMIN else 200)
    if role != Role.ADMIN:
        assert client.get("/api/receipts/pending").json["total"] == 1
    assert client.get(f"/api/receipts/{draft['id']}/history").status_code == (200 if role == Role.DEPOZIT else 403 if role == Role.ADMIN else 404)
    history = client.get(url + "/history")
    assert history.status_code == (403 if role == Role.ADMIN else 200)
    if role != Role.ADMIN:
        assert history.json["total"] >= 3
        assert history.headers["Cache-Control"] == "no-store"
        assert client.get(url + "/history?page=0").status_code == 400
        assert client.get(url + "/history?page=1&page=2").status_code == 400
    target = url + f"/items/{receipt['items'][0]['id']}"
    clarified = client.post(target + "/clarify", headers=headers, json={"version": 2, "reason": "Control", "purchase_order_item_id": data["order"]["items"][0]["id"]})
    assert clarified.status_code == (200 if role == Role.ACHIZITII else 403)
    decided = client.post(target + "/resolve", headers=headers, json={"version": 2, "reason": "Control", "action": "REJECT", "quantity": "1"})
    assert decided.status_code == (200 if role == Role.DEPOZIT else 403)
    if role != Role.DEPOZIT:
        assert client.post("/api/receipts/unordered", headers=headers, json={}).status_code == 403


def test_history_records_actors_reasons_and_decision_quantities(session, data):
    receipt = arrival(data)
    receipt = operation(data, receipt, "clarify").json["receipt"]
    receipt = operation(data, receipt, "resolve").json["receipt"]
    client, _ = authorize(data["users"][Role.CONTABILITATE])
    events = client.get(f"/api/receipts/{receipt['id']}/history?per_page=100").json["events"]
    accepted = next(event for event in events if event["action"] == "ACCEPT")
    assert accepted["actor_name"] == "DEPOZIT"
    assert accepted["actor_user_id"] == data["users"][Role.DEPOZIT]
    assert accepted["order_number"] == data["order"]["number"]
    assert accepted["reason"] == "Decizie documentata"
    assert accepted["before"]["pending_quantity"] == "10.000"
    assert accepted["after"]["pending_quantity"] == "4.000"
    assert any(event["action"] == "CLARIFY" and event["actor_name"] == "ACHIZITII" for event in events)
    assert all("password_hash" not in str(event) and "unit_price" not in str(event) for event in events)


def test_existing_pending_quantity_can_be_accepted_on_the_initial_order(session, data):
    receipt = create_receipt(actor_user_id=data["users"][Role.DEPOZIT], purchase_order_id=data["order"]["id"],
        delivery_reference="CONTROL", received_at="2026-10-21T08:00:00Z", items=[{
            "purchase_order_item_id": data["order"]["items"][0]["id"], "received_quantity": "10"}])
    receipt = confirm_receipt(actor_user_id=data["users"][Role.DEPOZIT], receipt_id=receipt["id"], version=1, reason="Control amanat", items=[{
        "id": receipt["items"][0]["id"], "accepted_quantity": "6", "rejected_quantity": "0", "pending_quantity": "4"}])
    response = operation(data, receipt, "resolve", quantity="4")
    assert response.status_code == 200, response.json
    assert response.json["receipt"]["items"][0]["total_accepted_quantity"] == "10.000"
    assert response.json["receipt"]["items"][0]["pending_order_item_id"] is None
    assert session.scalar(select(func.sum(StockMovement.quantity_delta))) == 10


def test_initial_confirmation_counts_previous_deferred_acceptances(session, data):
    receipt = arrival(data)
    receipt = operation(data, receipt, "clarify").json["receipt"]
    receipt = operation(data, receipt, "resolve").json["receipt"]
    client, headers = authorize(data["users"][Role.DEPOZIT])
    second = create_receipt(actor_user_id=data["users"][Role.DEPOZIT], purchase_order_id=data["order"]["id"],
        delivery_reference="ALTA-SOSIRE", received_at="2026-10-21T08:00:00Z", items=[{
            "purchase_order_item_id": data["order"]["items"][0]["id"], "received_quantity": "5"}])
    url = f"/api/receipts/{second['id']}/confirm"
    body = {"version": 1, "reason": "Control", "items": [{"id": second["items"][0]["id"],
        "accepted_quantity": "5", "rejected_quantity": "0", "pending_quantity": "0"}]}
    assert client.post(url, headers=headers, json=body).status_code == 409
    body["items"][0].update(accepted_quantity="4", pending_quantity="1")
    assert client.post(url, headers=headers, json=body).status_code == 200
    assert session.scalar(select(func.sum(StockMovement.quantity_delta))) == 10


@pytest.mark.parametrize("fail_on_call", [2, 3, 4])
def test_late_audit_failure_rolls_back_the_whole_acceptance(session, data, fail_on_call):
    from app.services.audit import record_audit

    receipt = arrival(data)
    receipt = operation(data, receipt, "clarify").json["receipt"]
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    calls = 0

    def fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise SQLAlchemyError("test")
        return record_audit(**kwargs)

    with patch("app.services.receipt_exceptions.record_audit", side_effect=fail):
        assert operation(data, receipt, "resolve").status_code == 503
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert session.scalar(select(func.count()).select_from(ReceiptItem)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
    original = session.get(ReceiptItem, receipt["items"][0]["id"])
    assert original.pending_quantity == 10 and original.resolved_quantity == 0
    assert session.get(Receipt, receipt["id"]).version == receipt["version"]


def test_unknown_goods_can_be_rejected_without_a_commercial_source(session, data):
    receipt = arrival(data, unknown=True)
    result = operation(data, receipt, "resolve", action="REJECT", quantity="10")
    assert result.status_code == 200
    assert result.json["receipt"]["items"][0]["rejected_quantity"] == "10.000"
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert session.scalar(select(func.count()).select_from(Product)) == 1


def test_exception_routes_validate_csrf_json_identifiers_and_pagination(session, data):
    receipt = arrival(data)
    client, headers = authorize(data["users"][Role.DEPOZIT])
    url = f"/api/receipts/{receipt['id']}/items/{receipt['items'][0]['id']}/resolve"
    body = {"version": 2, "reason": "Control", "action": "REJECT", "quantity": "1"}
    assert client.post(url, json=body).status_code == 401
    assert client.post(url, headers=headers, data="text").status_code == 415
    assert client.post(url, headers=headers, data="{", content_type="application/json").status_code == 400
    assert client.post(url, headers=headers, json={**body, "x": "x" * 66000}).status_code == 413
    assert client.post(url.replace(f"items/{receipt['items'][0]['id']}", "items/999999"), headers=headers, json=body).status_code == 404
    for endpoint in ("/api/receipts/pending", f"/api/receipts/{receipt['id']}/history"):
        for query in ("page=0", "per_page=101", "page=x", "page=1&page=2", "role=ADMIN"):
            assert client.get(endpoint + "?" + query).status_code == 400
        assert client.get(endpoint).headers["Cache-Control"] == "no-store"
