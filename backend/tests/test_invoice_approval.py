from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Invoice, Receipt, Role
from test_invoice_allocations import authorize, setup, url
from test_invoice_verification import cover, verify
from test_exchange_rates import xml


def approve(setup, *, version=3, **changes):
    return setup["client"].post(f'/api/invoices/{setup["invoice"]["id"]}/approve',
        json={"version": version, "reason": "Aprobare dupa control", **changes}, headers=setup["headers"])


def prepare(setup, session):
    allocation_id = cover(setup, session)
    assert verify(setup, 2).json["invoice"]["status"] == "VERIFIED"
    return allocation_id


def test_approve_records_actor_time_and_audit(setup, session):
    prepare(setup, session)
    response = approve(setup)
    assert response.status_code == 200
    result = response.json
    assert result["approved"] is True
    assert result["issues"] == []
    invoice = result["invoice"]
    assert (invoice["status"], invoice["version"]) == ("APPROVED", 4)
    assert invoice["approved_by_id"] == setup["users"][Role.CONTABILITATE]
    assert invoice["approved_at"] is not None
    assert invoice["total_ron"] == "14.28"
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "APPROVE"))
    assert event.reason == "Aprobare dupa control"
    assert event.before_data["status"] == "VERIFIED"
    assert event.after_data["approved_at"] == invoice["approved_at"]
    assert response.headers["Cache-Control"] == "no-store"


def test_approved_document_and_allocations_cannot_be_changed(setup, session):
    allocation_id = prepare(setup, session)
    assert approve(setup).status_code == 200
    assert approve(setup).status_code == 409
    assert approve(setup, version=4).status_code == 409
    assert verify(setup, 4).status_code == 409
    assert setup["client"].post(url(setup) + "/release", json={"version": 4, "reason": "Corectie", "allocation_ids": [allocation_id]}, headers=setup["headers"]).status_code == 409
    body = {**setup["data"], "version": 4, "reason": "Corectie", "items": []}
    assert setup["client"].patch(f'/api/invoices/{setup["invoice"]["id"]}', json=body, headers=setup["headers"]).status_code == 409
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "APPROVE")) == 1


def test_approval_rechecks_source_and_persists_new_blocker(setup, session):
    prepare(setup, session)
    session.get(Receipt, setup["receipt"]["id"]).confirmed_by_id = None
    session.commit()
    response = approve(setup)
    assert response.status_code == 409
    assert response.json["approved"] is False
    assert response.json["invoice"]["status"] == "BLOCKED"
    assert response.json["invoice"]["version"] == 4
    assert response.json["invoice"]["approved_at"] is None
    assert "RECEIPT_NOT_CONFIRMED" in {issue["code"] for issue in response.json["issues"]}
    assert session.get(Invoice, setup["invoice"]["id"]).status == "BLOCKED"
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "APPROVE")) == 0


def test_eur_approval_preserves_conversion_without_network(setup, session, monkeypatch):
    cover(setup, session, currency="EUR")
    monkeypatch.setattr("app.services.exchange_rates.download_year", lambda year: ("https://curs.bnr.ro/files/xml/years/nbrfxrates2026.xml", xml()))
    assert verify(setup, 2).json["invoice"]["status"] == "VERIFIED"
    with patch("app.services.exchange_rates.download_year", side_effect=AssertionError("Cursul exista local")):
        response = approve(setup)
    assert response.status_code == 200
    assert response.json["invoice"]["exchange_rate_value"] == "5.000000"
    assert response.json["invoice"]["total_ron"] == "71.40"


def test_approval_requires_verified_and_current_version(setup, session):
    assert approve(setup, version=1).status_code == 409
    assert verify(setup).json["invoice"]["status"] == "BLOCKED"
    assert approve(setup, version=2).status_code == 409


def test_approval_audit_failure_rolls_back(setup, session):
    prepare(setup, session)
    with patch("app.services.invoice_verification.record_audit", side_effect=ValueError("Audit indisponibil")):
        assert approve(setup).status_code == 400
    invoice = session.get(Invoice, setup["invoice"]["id"])
    assert (invoice.status, invoice.version) == ("VERIFIED", 3)
    assert invoice.approved_at is None
    assert invoice.approved_by_id is None


@pytest.mark.parametrize("role", list(Role))
def test_approval_permissions(setup, session, role):
    prepare(setup, session)
    client, headers = authorize(setup["users"][role])
    response = client.post(f'/api/invoices/{setup["invoice"]["id"]}/approve', json={"version": 3, "reason": "Control"}, headers=headers)
    assert response.status_code == (200 if role == Role.CONTABILITATE else 403)


@pytest.mark.parametrize("changes", [{"version": True}, {"version": 0}, {"reason": " "}, {"reason": "x" * 1001}, {"approved_by_id": 1}])
def test_invalid_approval(setup, session, changes):
    assert approve(setup, **changes).status_code == 400


def test_csrf_and_missing_invoice(setup, session):
    client, headers = setup["client"], setup["headers"]
    assert client.post(f'/api/invoices/{setup["invoice"]["id"]}/approve', json={"version": 1, "reason": "Control"}).status_code == 401
    assert client.post('/api/invoices/999999/approve', json={"version": 1, "reason": "Control"}, headers=headers).status_code == 404
