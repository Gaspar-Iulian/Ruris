from unittest.mock import patch

from flask import current_app
from flask_jwt_extended import create_access_token, get_csrf_token
import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Invoice, InvoiceItem, Product, Role, Supplier, User


def editable(data, invoice, **changes):
    return {**data, "version": invoice["version"], "reason": "Corectie factura",
            "items": [{key: item[key] for key in ("id", "product_id", "quantity", "unit_price", "vat_rate")}
                      for item in invoice["items"]], **changes}


def test_edit_recalculates_preserves_snapshot_and_rejects_stale_version(setup, session):
    client, data = setup
    headers = authorize(client, session)
    invoice = client.post("/api/invoices", json=data, headers=headers).json["invoice"]
    body = editable(data, invoice, number="002")
    body["items"][0]["quantity"] = "6"
    product = session.get(Product, data["items"][0]["product_id"])
    product.name = "Nume modificat"
    session.commit()
    url = f'/api/invoices/{invoice["id"]}'
    response = client.patch(url, json=body, headers=headers)
    assert response.status_code == 200
    result = response.json["invoice"]
    assert result["version"] == 2
    assert result["net_amount"] == "2.01"
    assert result["total_amount"] == "2.39"
    assert result["items"][0]["id"] == invoice["items"][0]["id"]
    assert result["items"][0]["description"] == "Produs initial"
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 4
    assert client.patch(url, json=body, headers=headers).status_code == 409
    assert client.get(url).json["invoice"] == result
    body = editable(data, result, number="002")
    assert client.patch(url, json=body, headers=headers).json["invoice"]["version"] == 2
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 4


def test_edit_add_remove_and_reorder_lines(setup, session):
    client, data = setup
    headers = authorize(client, session)
    data["items"] *= 3
    invoice = client.post("/api/invoices", json=data, headers=headers).json["invoice"]
    body = editable(data, invoice)
    removed_id = body["items"][1]["id"]
    body["items"] = [body["items"][2], body["items"][0], data["items"][0]]
    response = client.patch(f'/api/invoices/{invoice["id"]}', json=body, headers=headers)
    assert response.status_code == 200
    lines = response.json["invoice"]["items"]
    assert [line["line_number"] for line in lines] == [1, 2, 3]
    assert [line["id"] for line in lines[:2]] == [invoice["items"][2]["id"], invoice["items"][0]["id"]]
    assert session.get(InvoiceItem, removed_id) is None
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "DELETE"))
    assert event.entity_id == removed_id
    assert event.reason == "Corectie factura"


def test_reorder_full_draft_and_clear_all_lines(setup, session):
    client, data = setup
    headers = authorize(client, session)
    data["items"] *= 100
    invoice = client.post("/api/invoices", json=data, headers=headers).json["invoice"]
    url = f'/api/invoices/{invoice["id"]}'
    body = editable(data, invoice)
    body["items"].reverse()
    response = client.patch(url, json=body, headers=headers)
    assert response.status_code == 200
    result = response.json["invoice"]
    assert [item["id"] for item in result["items"]] == [item["id"] for item in reversed(invoice["items"])]
    response = client.patch(url, json=editable(data, result, items=[]), headers=headers)
    assert response.status_code == 200
    assert response.json["invoice"]["items"] == []
    assert response.json["invoice"]["total_amount"] == "0.00"


def test_header_only_edit_does_not_audit_unchanged_lines(setup, session):
    client, data = setup
    headers = authorize(client, session)
    invoice = client.post("/api/invoices", json=data, headers=headers).json["invoice"]
    response = client.patch(f'/api/invoices/{invoice["id"]}', json=editable(data, invoice, due_date="2026-12-01"), headers=headers)
    assert response.status_code == 200
    assert response.json["invoice"]["version"] == 2
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 3


@pytest.mark.parametrize("changes", [
    {"version": True}, {"version": 0}, {"reason": " "}, {"reason": "x" * 1001},
    {"status": "APPROVED"}, {"created_by_id": 1}, {"currency": "USD"},
    {"due_date": "2026-01-01"}, {"items": [{}]},
])
def test_invalid_edit_unchanged(setup, session, changes):
    client, data = setup
    headers = authorize(client, session)
    invoice = client.post("/api/invoices", json=data, headers=headers).json["invoice"]
    url = f'/api/invoices/{invoice["id"]}'
    assert client.patch(url, json=editable(data, invoice, **changes), headers=headers).status_code == 400
    assert client.get(url).json["invoice"] == invoice
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


def test_edit_rejects_foreign_duplicate_and_changed_product_lines(setup, session):
    client, data = setup
    headers = authorize(client, session)
    first = client.post("/api/invoices", json=data, headers=headers).json["invoice"]
    second = client.post("/api/invoices", json={**data, "number": "002"}, headers=headers).json["invoice"]
    url = f'/api/invoices/{first["id"]}'
    body = editable(data, first)
    body["items"][0]["id"] = second["items"][0]["id"]
    assert client.patch(url, json=body, headers=headers).status_code == 400
    body = editable(data, first)
    body["items"] *= 2
    assert client.patch(url, json=body, headers=headers).status_code == 400
    product = Product(sku="TEST-2", name="Alt produs", unit="BUC")
    session.add(product)
    session.flush()
    product_id = product.id
    session.commit()
    body = editable(data, first)
    body["items"][0]["product_id"] = product_id
    assert client.patch(url, json=body, headers=headers).status_code == 400
    assert client.get(url).json["invoice"] == first


def test_edit_duplicate_reference_and_audit_failure_roll_back(setup, session):
    client, data = setup
    headers = authorize(client, session)
    first = client.post("/api/invoices", json=data, headers=headers).json["invoice"]
    client.post("/api/invoices", json={**data, "number": "002"}, headers=headers)
    url = f'/api/invoices/{first["id"]}'
    assert client.patch(url, json=editable(data, first, number="002"), headers=headers).status_code == 409
    with patch("app.services.invoices.record_audit", side_effect=ValueError("Audit indisponibil")):
        assert client.patch(url, json=editable(data, first, items=[]), headers=headers).status_code == 400
    assert client.get(url).json["invoice"] == first
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 4


@pytest.mark.parametrize("role", list(Role))
def test_edit_permissions_and_csrf(setup, session, role):
    client, data = setup
    headers = authorize(client, session, role)
    body = {**data, "version": 1, "reason": "Corectie"}
    assert client.patch("/api/invoices/999", json=body, headers=headers).status_code == (404 if role == Role.CONTABILITATE else 403)
    if role == Role.CONTABILITATE:
        assert client.patch("/api/invoices/999", json=body).status_code == 401


@pytest.fixture
def setup(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    client = current_app.test_client()
    supplier = Supplier(name="Furnizor", tax_country="RO", tax_id="123456")
    product = Product(sku="TEST-1", name="Produs initial", unit="BUC")
    session.add_all([supplier, product])
    session.flush()
    data = {"supplier_id": supplier.id, "series": " ab ", "number": " 001 ",
            "invoice_date": "2026-10-20", "due_date": "2026-11-20", "currency": "EUR",
            "items": [{"product_id": product.id, "quantity": "3", "unit_price": "0.3350", "vat_rate": "19"}]}
    session.commit()
    return client, data


def authorize(client, session, role=Role.CONTABILITATE, *, active=True):
    user = User(name="Test", email=f"invoice-{role.value}@example.com", role=role,
                password_hash="unused", token_version=1, is_active=active)
    session.add(user)
    session.flush()
    user_id = user.id
    session.commit()
    token = create_access_token(identity=str(user_id), additional_claims={"token_version": 1})
    client.set_cookie("access_token_cookie", token, path="/api")
    return {"X-CSRF-TOKEN": get_csrf_token(token)}


def test_create_rounding_totals_audit_and_snapshot(setup, session):
    client, data = setup
    headers = authorize(client, session)
    response = client.post("/api/invoices", json=data, headers=headers)
    assert response.status_code == 201
    result = response.json["invoice"]
    assert (result["series"], result["number"], result["status"], result["version"]) == ("AB", "001", "DRAFT", 1)
    assert (result["net_amount"], result["vat_amount"], result["total_amount"]) == ("1.01", "0.19", "1.20")
    assert response.headers["Cache-Control"] == "no-store"
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2
    product = session.get(Product, data["items"][0]["product_id"])
    product.name = "Nume nou"
    session.commit()
    assert client.get(f'/api/invoices/{result["id"]}').json["invoice"]["items"][0]["description"] == "Produs initial"
    listing = client.get("/api/invoices?per_page=1").json
    assert listing["total"] == 1
    assert "items" not in listing["invoices"][0]


@pytest.mark.parametrize("role", list(Role))
def test_roles(setup, session, role):
    client, data = setup
    headers = authorize(client, session, role)
    allowed = role == Role.CONTABILITATE
    assert client.post("/api/invoices", json=data, headers=headers).status_code == (201 if allowed else 403)
    assert client.get("/api/invoices").status_code == (200 if allowed else 403)
    assert client.get("/api/invoices/999").status_code == (404 if allowed else 403)


@pytest.mark.parametrize("changes", [
    {"currency": "USD"}, {"currency": []}, {"series": None}, {"series": "A B"},
    {"number": " "}, {"number": "x" * 81}, {"series": "x" * 41},
    {"invoice_date": "2026-02-30"}, {"invoice_date": "20261020"},
    {"due_date": "2026-10-19"}, {"items": None}, {"items": [{}] * 101},
    {"status": "APPROVED"}, {"total_amount": "0"}, {"supplier_id": True},
])
def test_invalid_header_no_writes(setup, session, changes):
    client, data = setup
    headers = authorize(client, session)
    assert client.post("/api/invoices", json={**data, **changes}, headers=headers).status_code == 400
    assert session.scalar(select(func.count()).select_from(Invoice)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("changes", [
    {"quantity": "0"}, {"quantity": 1}, {"quantity": "NaN"}, {"quantity": "1.0001"},
    {"unit_price": "-1"}, {"unit_price": "1e2"}, {"unit_price": "1.00001"},
    {"vat_rate": "100.01"}, {"vat_rate": "-1"}, {"product_id": False},
    {"net_amount": "0"}, {"quantity": "999999999999999", "unit_price": "99999999999999"},
])
def test_invalid_line_no_writes(setup, session, changes):
    client, data = setup
    headers = authorize(client, session)
    data["items"][0].update(changes)
    assert client.post("/api/invoices", json=data, headers=headers).status_code == 400
    assert session.scalar(select(func.count()).select_from(InvoiceItem)) == 0


def test_duplicate_normalized_reference_and_empty_draft(setup, session):
    client, data = setup
    headers = authorize(client, session)
    assert client.post("/api/invoices", json=data, headers=headers).status_code == 201
    data.update(series="AB", number="001")
    assert client.post("/api/invoices", json=data, headers=headers).status_code == 409
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2
    data.update(series="", number="002", currency="RON", items=[])
    response = client.post("/api/invoices", json=data, headers=headers)
    assert response.status_code == 201
    assert response.json["invoice"]["total_amount"] == "0.00"


def test_audit_failure_rolls_back_entire_document(setup, session):
    client, data = setup
    headers = authorize(client, session)
    with patch("app.services.invoices.record_audit", side_effect=ValueError("Audit indisponibil")):
        assert client.post("/api/invoices", json=data, headers=headers).status_code == 400
    assert session.scalar(select(func.count()).select_from(Invoice)) == 0
    assert session.scalar(select(func.count()).select_from(InvoiceItem)) == 0


@pytest.mark.parametrize("catalog", ["product", "supplier"])
def test_inactive_catalog_rejected(setup, session, catalog):
    client, data = setup
    headers = authorize(client, session)
    obj = session.get(Product, data["items"][0]["product_id"]) if catalog == "product" else session.get(Supplier, data["supplier_id"])
    obj.is_active = False
    session.commit()
    assert client.post("/api/invoices", json=data, headers=headers).status_code == 400


def test_auth_csrf_and_pagination(setup, session):
    client, data = setup
    assert client.get("/api/invoices").status_code == 401
    authorize(client, session)
    assert client.post("/api/invoices", json=data).status_code == 401
    for query in ("page=0", "per_page=101", "page=a", "page=1&page=2", "status=DRAFT"):
        assert client.get(f"/api/invoices?{query}").status_code == 400
    assert client.get("/api/invoices/9223372036854775808").status_code == 404
