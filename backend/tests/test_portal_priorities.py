from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Role
from app.services.invoices import create_invoice
from app.services.purchase_orders import confirm_order, create_order
from app.services.receipts import confirm_receipt, create_receipt
from test_receipt_exceptions import arrival, authorize, data, operation


def order_for(data, *, due="2026-12-01", confirmed=True):
    order = create_order(actor_user_id=data["users"][Role.ACHIZITII], supplier_id=data["supplier_id"], currency="RON", items=[{
        "product_id": data["product_id"], "quantity": "10", "unit_price": "2", "vat_rate": "0", "expected_date": due}])
    return confirm_order(actor_user_id=data["users"][Role.ACHIZITII], order_id=order["id"], version=1) if confirmed else order


def receive(data, order, amount, *, confirmed=True, pending=False):
    receipt = create_receipt(actor_user_id=data["users"][Role.DEPOZIT], purchase_order_id=order["id"],
        delivery_reference="PRIORITY", received_at="2026-10-21T08:00:00Z",
        items=[{"purchase_order_item_id": order["items"][0]["id"], "received_quantity": str(amount)}])
    if not confirmed:
        return receipt
    return confirm_receipt(actor_user_id=data["users"][Role.DEPOZIT], receipt_id=receipt["id"], version=1,
        reason="Control prioritate", items=[{"id": receipt["items"][0]["id"], "accepted_quantity": "0" if pending else str(amount),
            "rejected_quantity": "0", "pending_quantity": str(amount) if pending else "0"}])


@pytest.mark.parametrize("role", [Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE])
def test_order_priority_is_applied_before_pagination(session, data, monkeypatch, role):
    monkeypatch.setattr("app.services.purchase_orders.bucharest_date", lambda: date(2026, 10, 21))
    complete = data["order"]
    receive(data, complete, 10)
    waiting = order_for(data)
    partial = order_for(data)
    receive(data, partial, 3)
    draft = order_for(data, confirmed=False)
    late = order_for(data, due="2026-10-01")
    client, _ = authorize(data["users"][role])
    expected = [late["id"], *([draft["id"]] if role == Role.ACHIZITII else []), partial["id"], waiting["id"], complete["id"]]
    pages = [client.get(f"/api/purchase-orders?page={page}&per_page=1").json for page in range(1, len(expected) + 1)]
    assert [page["orders"][0]["id"] for page in pages] == expected
    assert all(page["total"] == len(expected) for page in pages)
    if role == Role.DEPOZIT:
        assert all("unit_price" not in str(page) and "currency" not in str(page) for page in pages)


@pytest.mark.parametrize("role", [Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE])
def test_receipt_pending_and_draft_precede_resolved_receipts(session, data, role):
    resolved = receive(data, data["order"], 2)
    draft = receive(data, data["order"], 2, confirmed=False)
    pending = receive(data, data["order"], 2, pending=True)
    client, _ = authorize(data["users"][role])
    expected = [pending["id"], *([draft["id"]] if role == Role.DEPOZIT else []), resolved["id"]]
    pages = [client.get(f"/api/receipts?page={page}&per_page=1").json for page in range(1, len(expected) + 1)]
    assert [page["receipts"][0]["id"] for page in pages] == expected
    assert all(page["total"] == len(expected) for page in pages)


def test_blocked_invoice_precedes_draft_and_verified_even_on_first_page(session, data):
    receive(data, data["order"], 10)
    client, headers = authorize(data["users"][Role.CONTABILITATE])

    def invoice(number, due):
        return create_invoice(actor_user_id=data["users"][Role.CONTABILITATE], supplier_id=data["supplier_id"], series="PRIORITY", number=number,
            invoice_date="2026-10-21", due_date=due, currency="RON", items=[{"product_id": data["product_id"], "quantity": "1",
                "unit_price": "2", "vat_rate": "0", "purchase_order_item_id": data["order"]["items"][0]["id"]}],
            declared_totals={"net_amount": "2", "vat_amount": "0", "total_amount": "2"})

    draft = invoice("DRAFT", "2026-10-22")
    blocked = invoice("BLOCKED", "2026-12-01")
    response = client.post(f'/api/invoices/{blocked["id"]}/verify', headers=headers, json={"version": 1})
    assert response.status_code == 200
    assert client.get("/api/invoices?per_page=1").json["invoices"][0]["id"] == blocked["id"]
    assert client.get("/api/invoices?page=2&per_page=1").json["invoices"][0]["id"] == draft["id"]


def test_grouped_history_paginates_operations_without_losing_line_audit(session, data):
    receipt = arrival(data)
    client, _ = authorize(data["users"][Role.DEPOZIT])
    url = f'/api/receipts/{receipt["id"]}/history'
    raw = client.get(url + "?per_page=100").json
    before_count = session.scalar(select(func.count()).select_from(AuditEvent))
    first = client.get(url + "?grouped=1&per_page=1").json
    second = client.get(url + "?grouped=1&per_page=1&page=2").json
    assert first["total"] == second["total"] == 2
    assert first["events"][0]["action"] == "CONFIRM"
    assert second["events"][0]["action"] == "CREATE"
    visible_ids = {event["id"] for page in (first, second) for event in page["events"] for event in [event, *event["changes"]]}
    assert visible_ids == {event["id"] for event in raw["events"]}
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before_count
    assert client.get(url + "?grouped=yes").status_code == 400
    assert client.get(url + "?grouped=1&grouped=1").status_code == 400


def test_grouped_history_keeps_distinct_operations_in_the_same_second(session, data):
    receipt = arrival(data)
    for microsecond in (100000, 200000):
        session.add(AuditEvent(entity_type="receipts", entity_id=receipt["id"], action="UPDATE", actor_user_id=data["users"][Role.DEPOZIT],
            reason="Aceeasi observatie", created_at=datetime(2026, 10, 21, 10, 0, 0, microsecond, tzinfo=timezone.utc)))
    session.commit()
    client, _ = authorize(data["users"][Role.DEPOZIT])
    result = client.get(f'/api/receipts/{receipt["id"]}/history?grouped=1&per_page=100').json
    matching = [event for event in result["events"] if event["reason"] == "Aceeasi observatie"]
    assert len(matching) == 2
    assert matching[0]["created_at"] != matching[1]["created_at"]


def test_grouped_history_retains_partial_acceptance_and_reason(session, data):
    receipt = arrival(data, unknown=True)
    receipt = operation(data, receipt, "clarify").json["receipt"]
    receipt = operation(data, receipt, "resolve").json["receipt"]
    client, _ = authorize(data["users"][Role.CONTABILITATE])
    response = client.get(f'/api/receipts/{receipt["id"]}/history?grouped=1&per_page=100')
    assert response.status_code == 200
    accepted = next(event for event in response.json["events"] if event["action"] == "ACCEPT")
    assert accepted["before"]["pending_quantity"] == "10.000"
    assert accepted["after"]["pending_quantity"] == "4.000"
    assert accepted["reason"] == "Decizie documentata"
    assert any(event["is_acceptance"] for event in accepted["changes"])
