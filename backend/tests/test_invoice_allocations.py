from unittest.mock import patch

from flask import current_app
from flask_jwt_extended import create_access_token, get_csrf_token
import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, InvoiceAllocation, Product, Receipt, ReceiptItem, Role, Supplier, User
from app.services.invoices import create_invoice
from app.services.purchase_orders import confirm_order, create_order
from app.services.receipts import confirm_receipt, create_receipt


def authorize(user_id):
    client = current_app.test_client()
    token = create_access_token(identity=str(user_id), additional_claims={"token_version": 1})
    client.set_cookie("access_token_cookie", token, path="/api")
    return client, {"X-CSRF-TOKEN": get_csrf_token(token)}


def seed_data(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    users = {role: User(name=role.value, email=f"allocation-{role.value}@example.com", role=role,
                       password_hash="unused", token_version=1, is_active=True) for role in Role}
    supplier = Supplier(name="Furnizor", tax_country="RO", tax_id="123")
    product = Product(sku="P1", name="Produs", unit="BUC")
    session.add_all([*users.values(), supplier, product])
    session.flush()
    ids = {role: user.id for role, user in users.items()}
    supplier_id, product_id = supplier.id, product.id
    session.commit()
    order = create_order(actor_user_id=ids[Role.ACHIZITII], supplier_id=supplier_id, currency="EUR", items=[{
        "product_id": product_id, "quantity": "10", "unit_price": "2", "vat_rate": "19", "expected_date": "2026-10-20"}])
    order = confirm_order(actor_user_id=ids[Role.ACHIZITII], order_id=order["id"], version=1)
    receipt = create_receipt(actor_user_id=ids[Role.DEPOZIT], purchase_order_id=order["id"], delivery_reference="AV-1",
        received_at="2026-10-20T08:00:00Z", items=[{"purchase_order_item_id": order["items"][0]["id"], "received_quantity": "10"}])
    receipt = confirm_receipt(actor_user_id=ids[Role.DEPOZIT], receipt_id=receipt["id"], version=1, reason="Numarare",
        items=[{"id": receipt["items"][0]["id"], "accepted_quantity": "6", "pending_quantity": "3", "rejected_quantity": "1"}])
    data = {"supplier_id": supplier_id, "series": "AB", "number": "001", "invoice_date": "2026-10-20",
            "due_date": "2026-11-20", "currency": "EUR", "items": [
                {"product_id": product_id, "quantity": "10", "unit_price": "2", "vat_rate": "19"}]}
    invoice = create_invoice(actor_user_id=ids[Role.CONTABILITATE], **data)
    client, headers = authorize(ids[Role.CONTABILITATE])
    return {"client": client, "headers": headers, "users": ids, "invoice": invoice, "receipt": receipt, "data": data}


@pytest.fixture
def setup(session):
    return seed_data(session)


def payload(setup, *, invoice=None, quantity="4", version=1):
    invoice = invoice or setup["invoice"]
    return {"version": version, "reason": "Justificare factura", "items": [{
        "invoice_item_id": invoice["items"][0]["id"], "receipt_item_id": setup["receipt"]["items"][0]["id"], "quantity": quantity}]}


def url(setup):
    return f'/api/invoices/{setup["invoice"]["id"]}/allocations'


def test_allocate_partial_version_audit_and_edit_guard(setup, session):
    response = setup["client"].post(url(setup), json=payload(setup), headers=setup["headers"])
    assert response.status_code == 201
    result = response.json
    assert result["version"] == 2
    allocation = result["allocations"][0]
    assert allocation["quantity"] == "4.000"
    assert allocation["status"] == "ACTIVE"
    assert response.headers["Cache-Control"] == "no-store"
    event = session.scalar(select(AuditEvent).where(AuditEvent.entity_type == "invoice_allocations"))
    assert event.actor_user_id == setup["users"][Role.CONTABILITATE]
    assert event.reason == "Justificare factura"
    assert event.after_data == {key: value for key, value in allocation.items() if key != "id"}
    assert setup["client"].post(url(setup), json=payload(setup), headers=setup["headers"]).status_code == 409
    listing = setup["client"].get(url(setup)).json
    assert listing["allocations"] == [allocation]
    assert listing["total"] == 1
    invoice_url = f'/api/invoices/{setup["invoice"]["id"]}'
    assert setup["client"].get(invoice_url).json["invoice"]["status"] == "DRAFT"
    body = {**setup["data"], "version": 2, "reason": "Corectie", "items": []}
    assert setup["client"].patch(invoice_url, json=body, headers=setup["headers"]).status_code == 409


def test_accepted_capacity_shared_across_invoices(setup, session):
    client, headers = setup["client"], setup["headers"]
    assert client.post(url(setup), json=payload(setup), headers=headers).status_code == 201
    second = create_invoice(actor_user_id=setup["users"][Role.CONTABILITATE], **{**setup["data"], "number": "002"})
    second_url = f'/api/invoices/{second["id"]}/allocations'
    assert client.post(second_url, json=payload(setup, invoice=second, quantity="3"), headers=headers).status_code == 409
    assert client.post(second_url, json=payload(setup, invoice=second, quantity="2"), headers=headers).status_code == 201
    assert session.scalar(select(func.sum(InvoiceAllocation.quantity))) == 6
    assert client.post(url(setup), json=payload(setup, quantity="0.001", version=2), headers=headers).status_code == 409


def test_invoice_quantity_cannot_be_exceeded(setup, session):
    data = {**setup["data"], "number": "002", "items": [{**setup["data"]["items"][0], "quantity": "2"}]}
    invoice = create_invoice(actor_user_id=setup["users"][Role.CONTABILITATE], **data)
    response = setup["client"].post(f'/api/invoices/{invoice["id"]}/allocations',
        json=payload(setup, invoice=invoice, quantity="3"), headers=setup["headers"])
    assert response.status_code == 409
    assert session.scalar(select(func.count()).select_from(InvoiceAllocation)) == 0


@pytest.mark.parametrize("field,value", [("currency", "RON"), ("unit_price", "2.1"), ("vat_rate", "20")])
def test_order_financial_mismatch_rejected(setup, session, field, value):
    data = {**setup["data"], "number": "002", "items": [dict(setup["data"]["items"][0])]}
    if field == "currency":
        data[field] = value
    else:
        data["items"][0][field] = value
    invoice = create_invoice(actor_user_id=setup["users"][Role.CONTABILITATE], **data)
    response = setup["client"].post(f'/api/invoices/{invoice["id"]}/allocations', json=payload(setup, invoice=invoice), headers=setup["headers"])
    assert response.status_code == 409


@pytest.mark.parametrize("changes", [
    {"quantity": "0"}, {"quantity": "-1"}, {"quantity": 1}, {"quantity": "NaN"},
    {"quantity": "1.0001"}, {"receipt_item_id": True}, {"receipt_item_id": 999999},
    {"invoice_item_id": 999999}, {"status": "ACTIVE"},
])
def test_invalid_allocation_no_writes(setup, session, changes):
    body = payload(setup)
    body["items"][0].update(changes)
    assert setup["client"].post(url(setup), json=body, headers=setup["headers"]).status_code == 400
    assert session.scalar(select(func.count()).select_from(InvoiceAllocation)) == 0


@pytest.mark.parametrize("changes", [{"version": True}, {"version": 0}, {"reason": " "}, {"items": []}, {"items": None}, {"status": "APPROVED"}])
def test_invalid_header(setup, session, changes):
    assert setup["client"].post(url(setup), json={**payload(setup), **changes}, headers=setup["headers"]).status_code == 400


def test_duplicate_pairs_and_audit_failure_rollback(setup, session):
    client, headers = setup["client"], setup["headers"]
    body = payload(setup)
    body["items"] *= 2
    assert client.post(url(setup), json=body, headers=headers).status_code == 400
    with patch("app.services.invoice_allocations.record_audit", side_effect=ValueError("Audit indisponibil")):
        assert client.post(url(setup), json=payload(setup), headers=headers).status_code == 400
    assert session.scalar(select(func.count()).select_from(InvoiceAllocation)) == 0
    invoice = client.get(f'/api/invoices/{setup["invoice"]["id"]}').json["invoice"]
    assert invoice["version"] == 1


@pytest.mark.parametrize("role", list(Role))
def test_permissions(setup, session, role):
    client, headers = authorize(setup["users"][role])
    allowed = role == Role.CONTABILITATE
    assert client.post(url(setup), json=payload(setup), headers=headers).status_code == (201 if allowed else 403)
    assert client.get(url(setup)).status_code == (200 if allowed else 403)


def test_csrf_pagination_and_missing_invoice(setup, session):
    client = setup["client"]
    assert client.post(url(setup), json=payload(setup)).status_code == 401
    for query in ("page=0", "per_page=101", "page=a", "page=1&page=2", "status=ACTIVE"):
        assert client.get(url(setup) + "?" + query).status_code == 400
    assert client.get("/api/invoices/999999/allocations").status_code == 404


def test_unconfirmed_receipt_rejected(setup, session):
    receipt = session.get(Receipt, setup["receipt"]["id"])
    receipt.status = "DRAFT"
    session.commit()
    assert setup["client"].post(url(setup), json=payload(setup), headers=setup["headers"]).status_code == 409


def test_batch_cannot_overallocate_receipt_across_invoice_lines(setup, session):
    data = {**setup["data"], "number": "002", "items": setup["data"]["items"] * 2}
    invoice = create_invoice(actor_user_id=setup["users"][Role.CONTABILITATE], **data)
    body = payload(setup, invoice=invoice)
    body["items"].append({**body["items"][0], "invoice_item_id": invoice["items"][1]["id"]})
    response = setup["client"].post(f'/api/invoices/{invoice["id"]}/allocations', json=body, headers=setup["headers"])
    assert response.status_code == 409
    assert session.scalar(select(func.count()).select_from(InvoiceAllocation)) == 0


@pytest.mark.parametrize("mismatch", ["supplier", "product", "unit"])
def test_catalog_mismatch_rejected(setup, session, mismatch):
    data = {**setup["data"], "number": "002", "items": [dict(setup["data"]["items"][0])]}
    if mismatch == "supplier":
        supplier = Supplier(name="Alt furnizor", tax_country="RO", tax_id="999")
        session.add(supplier)
        session.flush()
        data["supplier_id"] = supplier.id
    elif mismatch == "product":
        product = Product(sku="P2", name="Alt produs", unit="BUC")
        session.add(product)
        session.flush()
        data["items"][0]["product_id"] = product.id
    else:
        received = session.get(ReceiptItem, setup["receipt"]["items"][0]["id"])
        received.unit = "KG"
    session.commit()
    invoice = create_invoice(actor_user_id=setup["users"][Role.CONTABILITATE], **data)
    response = setup["client"].post(f'/api/invoices/{invoice["id"]}/allocations', json=payload(setup, invoice=invoice), headers=setup["headers"])
    assert response.status_code == 409


def test_multiple_receipts_can_cover_one_invoice_line(setup, session):
    first = setup["client"].post(url(setup), json=payload(setup, quantity="6"), headers=setup["headers"])
    assert first.status_code == 201
    received = session.get(ReceiptItem, setup["receipt"]["items"][0]["id"])
    order_item_id = received.purchase_order_item_id
    from app.models import PurchaseOrderItem
    order_id = session.get(PurchaseOrderItem, order_item_id).purchase_order_id
    session.commit()
    receipt = create_receipt(actor_user_id=setup["users"][Role.DEPOZIT], purchase_order_id=order_id,
        delivery_reference="AV-2", received_at="2026-10-21T08:00:00Z",
        items=[{"purchase_order_item_id": order_item_id, "received_quantity": "4"}])
    receipt = confirm_receipt(actor_user_id=setup["users"][Role.DEPOZIT], receipt_id=receipt["id"], version=1,
        reason="Transa a doua", items=[{"id": receipt["items"][0]["id"], "accepted_quantity": "4", "rejected_quantity": "0", "pending_quantity": "0"}])
    body = payload(setup, quantity="4", version=2)
    body["items"][0]["receipt_item_id"] = receipt["items"][0]["id"]
    assert setup["client"].post(url(setup), json=body, headers=setup["headers"]).status_code == 201
    assert setup["client"].get(url(setup)).json["total"] == 2
