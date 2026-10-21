from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Invoice, InvoiceIssue, InvoiceItem, PurchaseOrder, PurchaseOrderItem, Receipt, ReceiptItem, Role
from app.services.invoices import create_invoice
from test_invoice_allocations import authorize, payload, setup, url
from app.services.exchange_rates import ExchangeRateUnavailable


@pytest.fixture(autouse=True)
def offline_exchange_rates(monkeypatch):
    def unavailable(requested_date):
        raise ExchangeRateUnavailable("Curs indisponibil in acest test.")
    monkeypatch.setattr("app.services.invoice_verification.get_eur_rate", unavailable)


def verify(setup, version=1):
    return setup["client"].post(f'/api/invoices/{setup["invoice"]["id"]}/verify', json={"version": version}, headers=setup["headers"])


def cover(setup, session, *, currency="RON"):
    line_id = setup["invoice"]["items"][0]["id"]
    invoice = session.get(Invoice, setup["invoice"]["id"])
    line = session.get(InvoiceItem, line_id)
    invoice.currency = currency
    line.quantity, line.net_amount, line.vat_amount, line.total_amount = 6, 12, "2.28", "14.28"
    invoice.net_amount, invoice.vat_amount, invoice.total_amount = 12, "2.28", "14.28"
    invoice.declared_net_amount, invoice.declared_vat_amount, invoice.declared_total_amount = 12, "2.28", "14.28"
    received = session.get(ReceiptItem, setup["receipt"]["items"][0]["id"])
    ordered = session.get(PurchaseOrderItem, received.purchase_order_item_id)
    session.get(PurchaseOrder, ordered.purchase_order_id).currency = currency
    session.commit()
    response = setup["client"].post(url(setup), json=payload(setup, quantity="6"), headers=setup["headers"])
    assert response.status_code == 201
    return response.json["allocations"][0]["id"]


def test_uncovered_eur_persists_multiple_issues_and_deduplicates(setup, session):
    response = verify(setup)
    assert response.status_code == 200
    result = response.json
    assert result["invoice"]["status"] == "BLOCKED"
    assert result["invoice"]["version"] == 2
    assert {issue["code"] for issue in result["issues"]} == {"QUANTITY_NOT_COVERED", "EXCHANGE_RATE_MISSING"}
    original = {issue["id"] for issue in result["issues"]}
    response = verify(setup, 2)
    assert {issue["id"] for issue in response.json["issues"]} == original
    assert session.scalar(select(func.count()).select_from(InvoiceIssue)) == 2
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "VERIFY")) == 2
    assert verify(setup, 2).status_code == 409


def test_fully_covered_ron_verified_and_release_invalidates(setup, session):
    allocation_id = cover(setup, session)
    response = verify(setup, 2)
    assert response.status_code == 200
    assert response.json["invoice"]["status"] == "VERIFIED"
    assert response.json["issues"] == []
    released = setup["client"].post(url(setup) + "/release", json={"version": 3, "reason": "Corectie", "allocation_ids": [allocation_id]}, headers=setup["headers"])
    assert released.status_code == 200
    invoice = setup["client"].get(f'/api/invoices/{setup["invoice"]["id"]}').json["invoice"]
    assert invoice["status"] == "DRAFT"
    assert verify(setup, 4).json["invoice"]["status"] == "BLOCKED"


def test_fully_covered_eur_waits_for_rate(setup, session):
    cover(setup, session, currency="EUR")
    result = verify(setup, 2).json
    assert result["invoice"]["status"] == "BLOCKED"
    assert [issue["code"] for issue in result["issues"]] == ["EXCHANGE_RATE_MISSING"]


def test_correction_supersedes_old_issues_and_reverification_creates_current_ones(setup, session):
    assert verify(setup).status_code == 200
    response = setup["client"].post(url(setup), json=payload(setup, version=2, quantity="4"), headers=setup["headers"])
    assert response.status_code == 201
    old = session.scalars(select(InvoiceIssue)).all()
    assert all(issue.resolution == "SUPERSEDED" and issue.resolved_at is not None for issue in old)
    assert verify(setup, 3).json["invoice"]["status"] == "BLOCKED"
    listing = setup["client"].get(f'/api/invoices/{setup["invoice"]["id"]}/issues').json
    assert listing["total"] == 4
    assert len([issue for issue in listing["issues"] if issue["resolved_at"] is None]) == 2


@pytest.mark.parametrize("problem,code", [
    ("receipt", "RECEIPT_NOT_CONFIRMED"), ("order", "ORDER_NOT_CONFIRMED"),
    ("capacity", "RECEIPT_OVERALLOCATED"), ("price", "TERMS_MISMATCH"),
    ("unit", "IDENTITY_MISMATCH"), ("line_total", "LINE_TOTAL_MISMATCH"),
    ("header_total", "INVOICE_TOTAL_MISMATCH"), ("source", "SOURCE_MISSING"),
])
def test_rechecks_current_documents_and_totals(setup, session, problem, code):
    cover(setup, session)
    receipt = session.get(Receipt, setup["receipt"]["id"])
    received = session.get(ReceiptItem, setup["receipt"]["items"][0]["id"])
    ordered = session.get(PurchaseOrderItem, received.purchase_order_item_id)
    invoice = session.get(Invoice, setup["invoice"]["id"])
    line = session.get(InvoiceItem, setup["invoice"]["items"][0]["id"])
    if problem == "receipt":
        receipt.confirmed_by_id = None
    elif problem == "order":
        session.get(PurchaseOrder, ordered.purchase_order_id).status = "CANCELLED"
    elif problem == "capacity":
        received.accepted_quantity, received.pending_quantity = 5, 4
    elif problem == "price":
        ordered.unit_price = 3
    elif problem == "unit":
        received.unit = "KG"
    elif problem == "line_total":
        line.net_amount, line.total_amount = 11, "13.28"
    elif problem == "header_total":
        invoice.net_amount, invoice.total_amount = 11, "13.28"
    else:
        received.purchase_order_item_id = None
    session.commit()
    result = verify(setup, 2).json
    assert result["invoice"]["status"] == "BLOCKED"
    assert code in {issue["code"] for issue in result["issues"]}


def test_empty_invoice_blocked(setup, session):
    invoice = create_invoice(actor_user_id=setup["users"][Role.CONTABILITATE], **{**setup["data"], "number": "002", "currency": "RON", "items": []})
    response = setup["client"].post(f'/api/invoices/{invoice["id"]}/verify', json={"version": 1}, headers=setup["headers"])
    assert "NO_ITEMS" in [issue["code"] for issue in response.json["issues"]]


def test_reverification_resolves_fixed_source_issue(setup, session):
    cover(setup, session)
    receipt = session.get(Receipt, setup["receipt"]["id"])
    receipt.confirmed_by_id = None
    session.commit()
    assert verify(setup, 2).json["invoice"]["status"] == "BLOCKED"
    receipt.confirmed_by_id = setup["users"][Role.DEPOZIT]
    session.commit()
    result = verify(setup, 3).json
    assert result["invoice"]["status"] == "VERIFIED"
    assert result["issues"] == []
    issue = session.scalar(select(InvoiceIssue))
    assert issue.resolution == "RESOLVED"
    assert issue.resolved_at is not None


def test_edit_blocked_invoice_invalidates_and_keeps_issue_history(setup, session):
    assert verify(setup).status_code == 200
    body = {**setup["data"], "version": 2, "reason": "Corectie cantitate", "items": [{
        **setup["data"]["items"][0], "id": setup["invoice"]["items"][0]["id"], "quantity": "6"}]}
    invoice_url = f'/api/invoices/{setup["invoice"]["id"]}'
    assert setup["client"].patch(invoice_url, json={**body, "items": []}, headers=setup["headers"]).status_code == 409
    response = setup["client"].patch(invoice_url, json=body, headers=setup["headers"])
    assert response.status_code == 200
    assert response.json["invoice"]["status"] == "DRAFT"
    assert response.json["invoice"]["version"] == 3
    assert all(issue.resolution == "SUPERSEDED" for issue in session.scalars(select(InvoiceIssue)).all())


def test_failed_verification_audit_rolls_back_issues_status_version(setup, session):
    with patch("app.services.invoice_verification.record_audit", side_effect=ValueError("Audit indisponibil")):
        assert verify(setup).status_code == 400
    invoice = session.get(Invoice, setup["invoice"]["id"])
    assert (invoice.status, invoice.version) == ("DRAFT", 1)
    assert session.scalar(select(func.count()).select_from(InvoiceIssue)) == 0


@pytest.mark.parametrize("role", list(Role))
def test_permissions(setup, session, role):
    client, headers = authorize(setup["users"][role])
    invoice_id = setup["invoice"]["id"]
    assert client.post(f"/api/invoices/{invoice_id}/verify", json={"version": 1}, headers=headers).status_code == (200 if role == Role.CONTABILITATE else 403)
    assert client.get(f"/api/invoices/{invoice_id}/issues").status_code == (200 if role == Role.CONTABILITATE else 403)


@pytest.mark.parametrize("data", [{}, {"version": True}, {"version": 0}, {"version": 2147483647}, {"version": 1, "status": "VERIFIED"}])
def test_invalid_verify_body(setup, session, data):
    assert setup["client"].post(f'/api/invoices/{setup["invoice"]["id"]}/verify', json=data, headers=setup["headers"]).status_code == 400


def test_csrf_missing_invoice_and_issue_pagination(setup, session):
    client, headers = setup["client"], setup["headers"]
    invoice_id = setup["invoice"]["id"]
    assert client.post(f"/api/invoices/{invoice_id}/verify", json={"version": 1}).status_code == 401
    assert client.post("/api/invoices/999999/verify", json={"version": 1}, headers=headers).status_code == 404
    assert client.get("/api/invoices/999999/issues").status_code == 404
    for query in ("page=0", "per_page=101", "page=a", "page=1&page=2", "role=ADMIN"):
        assert client.get(f"/api/invoices/{invoice_id}/issues?{query}").status_code == 400
