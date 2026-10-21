from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Invoice, InvoiceIssue, Role
from test_invoice_allocations import authorize, setup, url
from test_invoice_approval import approve, prepare
from test_invoice_verification import verify


def payload(**changes):
    return {"version": 4, "reason": "Plata conform extrasului", "payment_reference": " OP-123 ",
            "paid_at": datetime.now(timezone.utc).isoformat(), **changes}


def pay(setup, **changes):
    return setup["client"].post(f'/api/invoices/{setup["invoice"]["id"]}/pay', json=payload(**changes), headers=setup["headers"])


def approved(setup, session):
    allocation_id = prepare(setup, session)
    assert approve(setup).status_code == 200
    return allocation_id


def test_record_payment_and_preserve_approval_conversion(setup, session):
    approved(setup, session)
    response = pay(setup)
    assert response.status_code == 200
    result = response.json["invoice"]
    assert (result["status"], result["version"]) == ("PAID", 5)
    assert result["payment_reference"] == "OP-123"
    assert result["paid_by_id"] == setup["users"][Role.CONTABILITATE]
    assert result["paid_at"] is not None
    assert result["approved_at"] is not None
    assert result["total_ron"] == "14.28"
    assert result["exchange_rate_value"] == "1.000000"
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "PAY"))
    assert event.actor_user_id == result["paid_by_id"]
    assert event.reason == "Plata conform extrasului"
    assert event.before_data["status"] == "APPROVED"
    assert event.after_data["payment_reference"] == "OP-123"
    assert response.headers["Cache-Control"] == "no-store"
    assert setup["client"].get(f'/api/invoices/{result["id"]}').json["invoice"] == result


def test_payment_repeat_and_all_mutations_rejected(setup, session):
    allocation_id = approved(setup, session)
    assert pay(setup).status_code == 200
    assert pay(setup).status_code == 409
    assert pay(setup, version=5).status_code == 409
    assert approve(setup, version=5).status_code == 409
    assert verify(setup, 5).status_code == 409
    assert setup["client"].post(url(setup) + "/release", json={"version": 5, "reason": "Corectie", "allocation_ids": [allocation_id]}, headers=setup["headers"]).status_code == 409
    body = {**setup["data"], "version": 5, "reason": "Corectie", "items": []}
    assert setup["client"].patch(f'/api/invoices/{setup["invoice"]["id"]}', json=body, headers=setup["headers"]).status_code == 409
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "PAY")) == 1


@pytest.mark.parametrize("changes", [
    {"version": True}, {"version": 0}, {"reason": " "}, {"reason": "x" * 1001},
    {"paid_at": "2026-10-20"}, {"paid_at": "2026-10-20T12:00:00"},
    {"paid_at": "2026-02-30T10:00:00Z"}, {"paid_at": None},
    {"payment_reference": " "}, {"payment_reference": None}, {"payment_reference": "x" * 121},
    {"payment_reference": "OP\n123"}, {"amount": "1"}, {"paid_by_id": 1},
])
def test_invalid_payment_does_not_change_approval(setup, session, changes):
    approved(setup, session)
    assert pay(setup, **changes).status_code == 400
    invoice = session.get(Invoice, setup["invoice"]["id"])
    assert (invoice.status, invoice.version) == ("APPROVED", 4)
    assert invoice.paid_at is None


def test_payment_requires_approval_and_current_version(setup, session):
    assert pay(setup, version=1).status_code == 409
    prepare(setup, session)
    assert pay(setup, version=3).status_code == 409
    assert approve(setup).status_code == 200
    assert pay(setup, version=3).status_code == 409


def test_payment_time_after_approval_and_not_future(setup, session):
    approved(setup, session)
    invoice = session.get(Invoice, setup["invoice"]["id"])
    before_approval = (invoice.approved_at - timedelta(seconds=1)).isoformat()
    session.rollback()
    assert pay(setup, paid_at=before_approval).status_code == 400
    assert pay(setup, paid_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()).status_code == 400


def test_payment_audit_failure_rolls_back(setup, session):
    approved(setup, session)
    with patch("app.services.invoice_payments.record_audit", side_effect=ValueError("Audit indisponibil")):
        assert pay(setup).status_code == 400
    invoice = session.get(Invoice, setup["invoice"]["id"])
    assert (invoice.status, invoice.version) == ("APPROVED", 4)
    assert invoice.paid_by_id is None
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "PAY")) == 0


def test_open_issue_prevents_payment(setup, session):
    approved(setup, session)
    session.add(InvoiceIssue(invoice_id=setup["invoice"]["id"], code="REVIEW_REQUIRED", details="Clarificare noua", responsible_role="CONTABILITATE"))
    session.commit()
    assert pay(setup).status_code == 409


@pytest.mark.parametrize("role", list(Role))
def test_payment_role_permissions(setup, session, role):
    approved(setup, session)
    client, headers = authorize(setup["users"][role])
    response = client.post(f'/api/invoices/{setup["invoice"]["id"]}/pay', json=payload(), headers=headers)
    assert response.status_code == (200 if role == Role.CONTABILITATE else 403)


def test_csrf_and_missing_invoice(setup, session):
    client, headers = setup["client"], setup["headers"]
    assert client.post(f'/api/invoices/{setup["invoice"]["id"]}/pay', json=payload()).status_code == 401
    assert client.post('/api/invoices/999999/pay', json=payload(), headers=headers).status_code == 404
