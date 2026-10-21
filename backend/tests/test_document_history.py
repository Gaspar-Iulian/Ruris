from datetime import datetime, timezone

from sqlalchemy import func, select
import pytest

from app.models import AuditEvent, Role
from app.services.audit import record_audit
from app.services.invoices import create_invoice
from test_invoice_allocations import authorize
from test_receipt_exceptions import arrival, data, operation


@pytest.mark.parametrize("role", list(Role))
def test_order_history_respects_roles_and_redacts_commercial_snapshots(session, data, role):
    order = data["order"]
    record_audit(action="UPDATE", entity_type="purchase_order_items", entity_id=order["items"][0]["id"],
        actor_user_id=data["users"][Role.ACHIZITII], reason="Pret confidential 98765.4321", after={
            "purchase_order_id": order["id"], "line_number": 1, "unit_price": "98765.4321", "quantity": "10.000"})
    session.commit()
    client, _ = authorize(data["users"][role])
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    response = client.get(f"/api/purchase-orders/{order['id']}/history")
    assert response.status_code == (403 if role == Role.ADMIN else 200)
    if role == Role.ADMIN:
        return
    assert response.headers["Cache-Control"] == "no-store"
    assert any(event["action"] == "CONFIRM" for event in response.json["events"])
    if role == Role.DEPOZIT:
        text = str(response.json)
        assert "98765.4321" not in text
        assert "unit_price" not in text and "vat_rate" not in text and "currency" not in text
    else:
        assert "98765.4321" in str(response.json)
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_history_preserves_removed_order_lines_and_filters_other_documents(session, data):
    order = data["order"]
    for document_id, line_id in ((order["id"], 999999), (999998, 999998)):
        record_audit(action="DELETE", entity_type="purchase_order_items", entity_id=line_id,
            actor_user_id=data["users"][Role.ACHIZITII], before={"purchase_order_id": document_id, "line_number": 2,
                                                                  "description": f"Pozitie {line_id}"}, reason="Eliminare din ciorna")
    session.commit()
    client, _ = authorize(data["users"][Role.ACHIZITII])
    events = client.get(f"/api/purchase-orders/{order['id']}/history").json["events"]
    assert any(event["entity_id"] == 999999 and event["action"] == "DELETE" for event in events)
    assert all(event["entity_id"] != 999998 for event in events)


def test_invoice_history_includes_blockers_allocations_approval_and_payment(session, data):
    receipt = arrival(data)
    invoice = create_invoice(actor_user_id=data["users"][Role.CONTABILITATE], supplier_id=data["supplier_id"], series="", number="HISTORY",
        invoice_date="2026-10-21", due_date="2026-11-21", currency="RON", declared_totals={"net_amount": "12", "vat_amount": "0", "total_amount": "12"}, items=[{
            "product_id": data["product_id"], "quantity": "6", "unit_price": "2", "vat_rate": "0"}])
    client, headers = authorize(data["users"][Role.CONTABILITATE])
    url = f"/api/invoices/{invoice['id']}"
    assert client.post(url + "/verify", headers=headers, json={"version": 1}).json["invoice"]["status"] == "BLOCKED"
    receipt = operation(data, receipt, "clarify").json["receipt"]
    receipt = operation(data, receipt, "resolve").json["receipt"]
    allocated = client.post(url + "/allocations", headers=headers, json={"version": 2, "reason": "Marfa acceptata", "items": [{
        "invoice_item_id": invoice["items"][0]["id"], "receipt_item_id": receipt["items"][0]["acceptances"][0]["id"], "quantity": "6"}]})
    assert allocated.status_code == 201
    assert client.post(url + "/verify", headers=headers, json={"version": 3}).json["invoice"]["status"] == "VERIFIED"
    assert client.post(url + "/approve", headers=headers, json={"version": 4, "reason": "Control final"}).status_code == 200
    assert client.post(url + "/pay", headers=headers, json={"version": 5, "reason": "Plata efectuata",
        "paid_at": datetime.now(timezone.utc).isoformat(), "payment_reference": "OP-HISTORY"}).status_code == 200
    response = client.get(url + "/history?per_page=100")
    assert response.status_code == 200
    events = response.json["events"]
    assert {"CREATE", "VERIFY", "APPROVE", "PAY", "OPEN", "SUPERSEDE"} <= {event["action"] for event in events}
    assert any(event["entity_type"] == "invoice_allocations" for event in events)
    assert any(event["after"].get("payment_reference") == "OP-HISTORY" for event in events if event["after"])
    assert all(event["actor_name"] == "CONTABILITATE" for event in events)
    for role in (Role.ADMIN, Role.ACHIZITII, Role.DEPOZIT):
        other, _ = authorize(data["users"][role])
        assert other.get(url + "/history").status_code == 403


def test_history_pagination_missing_documents_and_auth(session, data):
    client, _ = authorize(data["users"][Role.CONTABILITATE])
    for prefix in ("/api/purchase-orders", "/api/invoices"):
        for query in ("page=0", "page=x", "per_page=101", "page=1&page=2", "role=ADMIN"):
            assert client.get(prefix + f"/{data['order']['id']}/history?" + query).status_code == 400
        assert client.get(prefix + "/999999/history").status_code == 404
        assert client.get(prefix + "/9223372036854775808/history").status_code == 404
    url = f"/api/purchase-orders/{data['order']['id']}/history"
    first = client.get(url + "?per_page=1").json
    second = client.get(url + "?per_page=1&page=2").json
    assert first["total"] == second["total"] and first["events"][0]["id"] != second["events"][0]["id"]
