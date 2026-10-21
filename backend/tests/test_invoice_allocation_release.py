from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, InvoiceAllocation, Role
from app.services.invoices import create_invoice
from test_invoice_allocations import authorize, payload, setup, url


def allocate(setup, *, quantity="4", version=1):
    response = setup["client"].post(url(setup), json=payload(setup, quantity=quantity, version=version), headers=setup["headers"])
    assert response.status_code == 201
    return response.json["allocations"][0]["id"]


def release_body(ids, *, version=2, **changes):
    return {"version": version, "reason": "Legatura gresita", "allocation_ids": ids, **changes}


def edit_body(setup, version):
    return {**setup["data"], "version": version, "reason": "Corectie dupa eliberare", "items": [{
        **setup["data"]["items"][0], "id": setup["invoice"]["items"][0]["id"], "quantity": "8"}]}


def test_release_preserves_history_and_restores_capacity(setup, session):
    allocation_id = allocate(setup)
    client, headers = setup["client"], setup["headers"]
    response = client.post(url(setup) + "/release", json=release_body([allocation_id]), headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    result = response.json
    assert result["version"] == 3
    released = result["allocations"][0]
    assert released["status"] == "RELEASED"
    assert released["quantity"] == "4.000"
    assert released["released_at"] is not None
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "RELEASE"))
    assert event.actor_user_id == setup["users"][Role.CONTABILITATE]
    assert event.reason == "Legatura gresita"
    assert event.before_data["status"] == "ACTIVE"
    assert event.after_data["released_at"] == released["released_at"]
    assert client.get(url(setup)).json["allocations"] == [released]
    second = create_invoice(actor_user_id=setup["users"][Role.CONTABILITATE], **{**setup["data"], "number": "002"})
    response = client.post(f'/api/invoices/{second["id"]}/allocations',
                           json=payload(setup, invoice=second, quantity="6"), headers=headers)
    assert response.status_code == 201
    assert session.scalar(select(func.sum(InvoiceAllocation.quantity)).where(InvoiceAllocation.status == "ACTIVE")) == 6
    assert session.scalar(select(func.count()).select_from(InvoiceAllocation)) == 2


def test_edit_after_release_retains_referenced_lines(setup, session):
    allocation_id = allocate(setup)
    client, headers = setup["client"], setup["headers"]
    assert client.post(url(setup) + "/release", json=release_body([allocation_id]), headers=headers).status_code == 200
    invoice_url = f'/api/invoices/{setup["invoice"]["id"]}'
    body = edit_body(setup, 3)
    assert client.patch(invoice_url, json={**body, "items": []}, headers=headers).status_code == 409
    response = client.patch(invoice_url, json=body, headers=headers)
    assert response.status_code == 200
    assert response.json["invoice"]["version"] == 4
    assert response.json["invoice"]["items"][0]["quantity"] == "8.000"
    assert session.get(InvoiceAllocation, allocation_id).status == "RELEASED"
    assert client.post(url(setup), json=payload(setup, quantity="6", version=4), headers=headers).status_code == 201


def test_partial_selection_leaves_other_allocations_active(setup, session):
    first = allocate(setup, quantity="2")
    second = allocate(setup, quantity="2", version=2)
    client, headers = setup["client"], setup["headers"]
    response = client.post(url(setup) + "/release", json=release_body([first], version=3), headers=headers)
    assert response.status_code == 200
    assert session.get(InvoiceAllocation, second).status == "ACTIVE"
    assert client.patch(f'/api/invoices/{setup["invoice"]["id"]}', json=edit_body(setup, 4), headers=headers).status_code == 409
    response = client.post(url(setup) + "/release", json=release_body([first, second], version=4), headers=headers)
    assert response.status_code == 409
    assert session.get(InvoiceAllocation, second).status == "ACTIVE"


def test_release_repeat_and_old_version_rejected_without_extra_audit(setup, session):
    allocation_id = allocate(setup)
    client, headers = setup["client"], setup["headers"]
    body = release_body([allocation_id])
    assert client.post(url(setup) + "/release", json=body, headers=headers).status_code == 200
    assert client.post(url(setup) + "/release", json=body, headers=headers).status_code == 409
    assert client.post(url(setup) + "/release", json={**body, "version": 3}, headers=headers).status_code == 409
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "RELEASE")) == 1


@pytest.mark.parametrize("changes", [
    {"version": True}, {"version": 0}, {"version": 2147483647}, {"reason": " "},
    {"reason": "x" * 1001}, {"reason": None}, {"allocation_ids": []}, {"allocation_ids": None},
    {"allocation_ids": [True]}, {"allocation_ids": ["1"]}, {"allocation_ids": [0]},
    {"allocation_ids": [1] * 101}, {"status": "RELEASED"},
])
def test_invalid_release_unchanged(setup, session, changes):
    allocation_id = allocate(setup)
    response = setup["client"].post(url(setup) + "/release", json=release_body([allocation_id], **changes), headers=setup["headers"])
    assert response.status_code == 400
    assert session.get(InvoiceAllocation, allocation_id).status == "ACTIVE"


def test_unknown_foreign_and_duplicate_ids_rejected(setup, session):
    allocation_id = allocate(setup)
    client, headers = setup["client"], setup["headers"]
    for ids in ([allocation_id, allocation_id], [allocation_id, 999999]):
        assert client.post(url(setup) + "/release", json=release_body(ids), headers=headers).status_code == 400
    second = create_invoice(actor_user_id=setup["users"][Role.CONTABILITATE], **{**setup["data"], "number": "002"})
    response = client.post(f'/api/invoices/{second["id"]}/allocations/release',
        json=release_body([allocation_id], version=1), headers=headers)
    assert response.status_code == 400
    assert session.get(InvoiceAllocation, allocation_id).status == "ACTIVE"


def test_audit_failure_rolls_back_release_and_version(setup, session):
    allocation_id = allocate(setup, quantity="2")
    second_id = allocate(setup, quantity="2", version=2)
    client, headers = setup["client"], setup["headers"]
    from app.services.audit import record_audit

    def fail_header_audit(**kwargs):
        if kwargs["entity_type"] == "invoices":
            raise ValueError("Audit indisponibil")
        return record_audit(**kwargs)

    with patch("app.services.invoice_allocations.record_audit", side_effect=fail_header_audit):
        assert client.post(url(setup) + "/release", json=release_body([allocation_id, second_id], version=3), headers=headers).status_code == 400
    allocation = session.get(InvoiceAllocation, allocation_id)
    assert allocation.status == "ACTIVE"
    assert allocation.released_at is None
    assert session.get(InvoiceAllocation, second_id).status == "ACTIVE"
    assert client.get(url(setup)).json["version"] == 3
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "RELEASE")) == 0


@pytest.mark.parametrize("role", list(Role))
def test_release_permissions(setup, session, role):
    allocation_id = allocate(setup)
    client, headers = authorize(setup["users"][role])
    assert client.post(url(setup) + "/release", json=release_body([allocation_id]), headers=headers).status_code == (200 if role == Role.CONTABILITATE else 403)


def test_release_csrf_and_missing_invoice(setup, session):
    allocation_id = allocate(setup)
    client, headers = setup["client"], setup["headers"]
    assert client.post(url(setup) + "/release", json=release_body([allocation_id])).status_code == 401
    assert client.post("/api/invoices/999999/allocations/release", json=release_body([allocation_id]), headers=headers).status_code == 404
