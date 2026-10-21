import pytest
from sqlalchemy import select

from app.models import AuditEvent, InvoiceItem, Role
from app.services.purchase_orders import create_order, confirm_order
from test_invoice_allocations import authorize, payload, setup, url


def linked_data(setup, **changes):
    return {**setup["data"], "number": "LINK-002", "items": [{**setup["data"]["items"][0],
        "purchase_order_item_id": setup["receipt"]["items"][0]["purchase_order_item_id"]}], **changes}


def test_invoice_keeps_order_source_and_actual_document_terms(session, setup):
    data = linked_data(setup, currency="RON")
    data["items"][0]["unit_price"] = "3.1234"
    result = setup["client"].post("/api/invoices", headers=setup["headers"], json=data)
    assert result.status_code == 201
    invoice = result.json["invoice"]
    line = invoice["items"][0]
    source_id = data["items"][0]["purchase_order_item_id"]
    assert line["purchase_order_item_id"] == source_id
    assert line["quantity"] == "10.000"
    assert line["unit_price"] == "3.1234"
    assert invoice["currency"] == "RON"
    assert invoice["status"] == "DRAFT"
    assert session.get(InvoiceItem, line["id"]).purchase_order_item_id == source_id
    audit = session.scalar(select(AuditEvent).where(AuditEvent.entity_type == "invoice_items", AuditEvent.entity_id == line["id"]))
    assert audit.after_data["purchase_order_item_id"] == source_id
    edit = {**data, "version": 1, "reason": "Corectie", "items": [{**data["items"][0], "id": line["id"], "quantity": "9"}]}
    del edit["items"][0]["purchase_order_item_id"]
    updated = setup["client"].patch(f"/api/invoices/{invoice['id']}", headers=setup["headers"], json=edit)
    assert updated.status_code == 200
    assert updated.json["invoice"]["items"][0]["purchase_order_item_id"] == source_id


def test_invoicing_context_counts_active_allocations_only(session, setup):
    source_id = setup["receipt"]["items"][0]["purchase_order_item_id"]
    from app.models import PurchaseOrderItem
    order_id = session.get(PurchaseOrderItem, source_id).purchase_order_id
    context_url = f"/api/purchase-orders/{order_id}/invoicing"
    before = setup["client"].get(context_url)
    assert before.status_code == 200
    line = before.json["order"]["items"][0]
    assert (line["quantity"], line["accepted_quantity"], line["allocated_quantity"], line["available_quantity"]) == ("10.000", "6.000", "0.000", "6.000")
    result = setup["client"].post(url(setup), headers=setup["headers"], json=payload(setup))
    assert result.status_code == 201
    line = setup["client"].get(context_url).json["order"]["items"][0]
    assert (line["allocated_quantity"], line["available_quantity"]) == ("4.000", "2.000")
    assert setup["client"].post(url(setup) + "/release", headers=setup["headers"], json={"version": 2, "reason": "Corectie", "allocation_ids": [result.json["allocations"][0]["id"]]}).status_code == 200
    assert setup["client"].get(context_url).json["order"]["items"][0]["available_quantity"] == "6.000"


@pytest.mark.parametrize("role", list(Role))
def test_invoicing_context_is_accounting_only(session, setup, role):
    from app.models import PurchaseOrderItem
    order_id = session.get(PurchaseOrderItem, setup["receipt"]["items"][0]["purchase_order_item_id"]).purchase_order_id
    client, _ = authorize(setup["users"][role])
    assert client.get(f"/api/purchase-orders/{order_id}/invoicing").status_code == (200 if role == Role.CONTABILITATE else 403)


@pytest.mark.parametrize("source", [999999, 0, True, "1"])
def test_rejects_invalid_source_without_creating_invoice(session, setup, source):
    data = linked_data(setup)
    data["items"][0]["purchase_order_item_id"] = source
    assert setup["client"].post("/api/invoices", headers=setup["headers"], json=data).status_code == 400


def test_rejects_draft_order_and_allocations_from_another_order(session, setup):
    data = setup["data"]
    order = create_order(actor_user_id=setup["users"][Role.ACHIZITII], supplier_id=data["supplier_id"], currency="EUR", items=[{
        **data["items"][0], "expected_date": "2026-10-20",
    }])
    linked = linked_data(setup)
    linked["items"][0]["purchase_order_item_id"] = order["items"][0]["id"]
    assert setup["client"].post("/api/invoices", headers=setup["headers"], json=linked).status_code == 400
    confirm_order(actor_user_id=setup["users"][Role.ACHIZITII], order_id=order["id"], version=1)
    response = setup["client"].post("/api/invoices", headers=setup["headers"], json=linked)
    assert response.status_code == 201
    wrong = payload(setup, invoice=response.json["invoice"])
    assert setup["client"].post(f"/api/invoices/{response.json['invoice']['id']}/allocations", headers=setup["headers"], json=wrong).status_code == 409
