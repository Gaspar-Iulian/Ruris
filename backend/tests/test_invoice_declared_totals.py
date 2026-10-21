from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent, Invoice, InvoiceAllocation, InvoiceIssue, Role
from test_invoice_allocations import authorize, setup
from test_invoice_verification import cover, verify


TOTALS = {"net_amount": "12.00", "vat_amount": "2.28", "total_amount": "14.28"}


def totals_url(setup):
    return f'/api/invoices/{setup["invoice"]["id"]}/declared-totals'


def correct(setup, *, version=3, totals=TOTALS, reason="Corectie dupa document"):
    return setup["client"].patch(totals_url(setup), headers=setup["headers"], json={
        "version": version, "reason": reason, "declared_totals": totals})


def test_missing_totals_block_then_correction_keeps_allocations_and_audit(setup, session):
    allocation_id = cover(setup, session)
    invoice = session.get(Invoice, setup["invoice"]["id"])
    invoice.declared_net_amount = invoice.declared_vat_amount = invoice.declared_total_amount = None
    session.commit()
    blocked = verify(setup, 2).json
    assert [issue["code"] for issue in blocked["issues"]] == ["DECLARED_TOTALS_MISSING"]
    result = correct(setup)
    assert result.status_code == 200
    assert result.json["invoice"]["status"] == "DRAFT"
    assert result.json["invoice"]["total_ron"] is None
    assert result.json["invoice"]["declared_totals"] == TOTALS
    assert session.get(InvoiceAllocation, allocation_id).status == "ACTIVE"
    assert session.scalar(select(InvoiceIssue)).resolution == "SUPERSEDED"
    event = session.scalars(select(AuditEvent).where(AuditEvent.entity_type == "invoices", AuditEvent.action == "UPDATE")).all()[-1]
    assert event.reason == "Corectie dupa document"
    assert event.before_data["declared_totals"] is None
    assert event.after_data["declared_totals"] == TOTALS
    assert verify(setup, 4).json["invoice"]["status"] == "VERIFIED"
    assert correct(setup).status_code == 409


@pytest.mark.parametrize("field,code", [("net_amount", "DECLARED_NET_AMOUNT_MISMATCH"),
    ("vat_amount", "DECLARED_VAT_AMOUNT_MISMATCH"), ("total_amount", "DECLARED_TOTAL_AMOUNT_MISMATCH")])
def test_one_cent_difference_and_inconsistent_document_block_payment(setup, session, field, code):
    cover(setup, session)
    totals = {**TOTALS, field: format(Decimal(TOTALS[field]) + Decimal("0.01"), ".2f")}
    assert correct(setup, version=2, totals=totals).status_code == 200
    result = verify(setup, 3).json
    assert result["invoice"]["status"] == "BLOCKED"
    assert {issue["code"] for issue in result["issues"]} == {code, "DECLARED_TOTALS_INCONSISTENT"}
    assert result["invoice"]["totals_difference"][field] == "0.01"
    url = f'/api/invoices/{setup["invoice"]["id"]}'
    assert setup["client"].post(url + "/approve", headers=setup["headers"], json={"version": 4, "reason": "Plata"}).status_code == 409
    assert correct(setup, version=4).status_code == 200
    assert verify(setup, 5).json["invoice"]["status"] == "VERIFIED"


@pytest.mark.parametrize("totals", [{}, {"net_amount": "12"}, {**TOTALS, "extra": "0"},
    {**TOTALS, "net_amount": "NaN"}, {**TOTALS, "net_amount": "-1"},
    {**TOTALS, "vat_amount": "2.281"}, {**TOTALS, "total_amount": 14.28},
    {**TOTALS, "net_amount": "10000000000000000"}, [], True])
def test_invalid_totals_are_atomic(setup, session, totals):
    before = setup["client"].get(f'/api/invoices/{setup["invoice"]["id"]}').json
    count = session.scalar(select(func.count()).select_from(AuditEvent))
    assert correct(setup, version=1, totals=totals).status_code == 400
    assert setup["client"].get(f'/api/invoices/{setup["invoice"]["id"]}').json == before
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == count


@pytest.mark.parametrize("role", list(Role))
def test_roles_and_csrf(setup, role):
    client, headers = authorize(setup["users"][role])
    body = {"version": 1, "reason": "Corectie", "declared_totals": TOTALS}
    response = client.patch(totals_url(setup), headers=headers, json=body)
    assert response.status_code == (200 if role == Role.CONTABILITATE else 403)
    if role == Role.CONTABILITATE:
        assert client.patch(totals_url(setup), json=body).status_code == 401


def test_no_op_audit_failure_and_approved_immutability(setup, session):
    cover(setup, session)
    assert verify(setup, 2).json["invoice"]["status"] == "VERIFIED"
    count = session.scalar(select(func.count()).select_from(AuditEvent))
    assert correct(setup).json["invoice"]["version"] == 3
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == count
    with patch("app.services.invoices.record_audit", side_effect=ValueError("Audit unavailable")):
        assert correct(setup, totals={**TOTALS, "total_amount": "14.29"}).status_code == 400
    assert session.get(Invoice, setup["invoice"]["id"]).status == "VERIFIED"
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == count
    approved = setup["client"].post(f'/api/invoices/{setup["invoice"]["id"]}/approve', headers=setup["headers"], json={"version": 3, "reason": "Documente corecte"})
    assert approved.status_code == 200
    assert correct(setup, version=4, totals=None).status_code == 409


def test_database_rejects_partial_or_negative_totals(setup, session):
    for assignment in ("declared_net_amount = NULL", "declared_total_amount = -1", "declared_vat_amount = 'NaN'::numeric"):
        with pytest.raises(DBAPIError), session.begin_nested():
            session.execute(text(f"UPDATE invoices SET {assignment} WHERE id = :id"), {"id": setup["invoice"]["id"]})


def test_approval_rechecks_supplier_totals(setup, session):
    cover(setup, session)
    assert verify(setup, 2).json["invoice"]["status"] == "VERIFIED"
    invoice = session.get(Invoice, setup["invoice"]["id"])
    invoice.declared_total_amount = Decimal("14.29")
    session.commit()
    response = setup["client"].post(f'/api/invoices/{invoice.id}/approve', headers=setup["headers"], json={"version": 3, "reason": "Reverificare"})
    assert response.status_code == 409
    assert response.json["invoice"]["status"] == "BLOCKED"
