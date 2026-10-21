from copy import deepcopy
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Role
from app.services.exchange_rates import ExchangeRateUnavailable
from test_invoice_allocations import authorize, payload, setup, url


def endpoint(setup):
    return f"/api/invoices/{setup['invoice']['id']}/matching"


def test_matching_reports_receipts_coverage_and_reserved_quantities(session, setup):
    client = setup["client"]
    result = client.get(endpoint(setup))
    assert result.status_code == 200
    data = result.json
    assert data["invoice"] == setup["invoice"]
    line = data["items"][0]
    assert line["remaining_quantity"] == "10.000"
    candidate = line["candidates"][0]
    assert candidate["receipt_item_id"] == setup["receipt"]["items"][0]["id"]
    assert candidate["accepted_quantity"] == candidate["available_quantity"] == "6.000"
    assert candidate["eligible"] is True
    assert candidate["differences"] == []
    created = client.post(url(setup), headers=setup["headers"], json=payload(setup))
    assert created.status_code == 201
    data = client.get(endpoint(setup)).json
    assert data["items"][0]["allocated_quantity"] == "4.000"
    assert data["items"][0]["remaining_quantity"] == "6.000"
    assert data["items"][0]["candidates"][0]["available_quantity"] == "2.000"
    assert len(data["allocations"]) == 1
    assert client.post(url(setup) + "/release", headers=setup["headers"], json={
        "version": 2, "reason": "Corectie", "allocation_ids": [created.json["allocations"][0]["id"]],
    }).status_code == 200
    assert client.get(endpoint(setup)).json["items"][0]["candidates"][0]["available_quantity"] == "6.000"


@pytest.mark.parametrize("change,code", [("price", "PRICE"), ("vat", "VAT"), ("currency", "CURRENCY")])
def test_matching_shows_commercial_differences(session, setup, change, code):
    data = deepcopy(setup["data"])
    data["number"] = "DIFF-001"
    if change == "price":
        data["items"][0]["unit_price"] = "3"
    elif change == "vat":
        data["items"][0]["vat_rate"] = "10"
    else:
        data["currency"] = "RON"
    response = setup["client"].post("/api/invoices", headers=setup["headers"], json=data)
    assert response.status_code == 201
    result = setup["client"].get(f"/api/invoices/{response.json['invoice']['id']}/matching").json
    candidate = result["items"][0]["candidates"][0]
    assert candidate["eligible"] is False
    assert candidate["differences"] == [code]


@pytest.mark.parametrize("role", list(Role))
def test_matching_is_accounting_only(session, setup, role):
    client, _ = authorize(setup["users"][role])
    result = client.get(endpoint(setup))
    assert result.status_code == (200 if role == Role.CONTABILITATE else 403)


def test_matching_is_read_only_and_reports_blockers(session, setup):
    with patch("app.services.invoice_verification.get_eur_rate", side_effect=ExchangeRateUnavailable("Curs indisponibil in test")):
        result = setup["client"].post(f"/api/invoices/{setup['invoice']['id']}/verify", headers=setup["headers"], json={"version": 1})
    assert result.status_code == 200
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    for _ in range(2):
        data = setup["client"].get(endpoint(setup)).json
        assert data["invoice"]["version"] == 2
        assert any(issue["code"] == "QUANTITY_NOT_COVERED" for issue in data["issues"])
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
    assert setup["client"].get("/api/invoices/99999/matching").status_code == 404
