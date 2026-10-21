from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import current_app
import pytest
from sqlalchemy import func, select

from app.models import EmailAttempt, EmailOutbox, Role, User
from app.services.email_delivery import claim_delivery, queue_digest, recover_stale_deliveries, send_notification_digests, send_notification_digests_local
from app.services.receipt_notifications import build_buyer_receipt_digests, build_warehouse_receipt_digests
from test_invoice_allocations import authorize
from test_receipt_exceptions import arrival, data, new_order, operation


def test_unordered_goods_notify_buyers_then_warehouse_after_linking(session, data):
    receipt = arrival(data, unknown=True)
    buyer = build_buyer_receipt_digests()
    assert len(buyer["messages"]) == 1
    assert buyer["messages"][0]["recipient_user_id"] == data["users"][Role.ACHIZITII]
    assert "10.000 BUC" in buyer["messages"][0]["body"]
    assert build_warehouse_receipt_digests()["messages"] == []
    receipt = operation(data, receipt, "clarify").json["receipt"]
    assert build_buyer_receipt_digests()["messages"] == []
    warehouse = build_warehouse_receipt_digests()["messages"]
    assert len(warehouse) == 1 and warehouse[0]["recipient_user_id"] == data["users"][Role.DEPOZIT]
    assert receipt["number"] in warehouse[0]["body"] and "10.000 BUC" in warehouse[0]["body"]
    receipt = operation(data, receipt, "resolve").json["receipt"]
    assert "4.000 BUC" in build_warehouse_receipt_digests()["messages"][0]["body"]
    operation(data, receipt, "resolve", action="REJECT", quantity="4")
    assert build_warehouse_receipt_digests()["messages"] == build_buyer_receipt_digests()["messages"] == []


def test_shared_order_capacity_is_not_repeated_across_receipts(session, data):
    first, second = arrival(data), arrival(data)
    operation(data, first, "clarify")
    operation(data, second, "clarify")
    ready = build_warehouse_receipt_digests()["messages"][0]
    buyer = build_buyer_receipt_digests()["messages"][0]
    assert ready["item_count"] == 1 and buyer["item_count"] == 1
    assert first["number"] in ready["body"] and second["number"] in buyer["body"]


def test_partial_coverage_splits_responsibilities_without_prices(session, data):
    receipt = arrival(data)
    smaller = new_order(data, "6")
    operation(data, receipt, "clarify", purchase_order_item_id=smaller["items"][0]["id"])
    assert "6.000 BUC" in build_warehouse_receipt_digests()["messages"][0]["body"]
    assert "4.000 BUC" in build_buyer_receipt_digests()["messages"][0]["body"]
    for digest in (build_buyer_receipt_digests(), build_warehouse_receipt_digests()):
        assert "unit_price" not in str(digest) and "password" not in str(digest) and "TVA" not in str(digest)


def test_changed_clarification_is_skipped_and_four_channels_are_deduplicated(session, data):
    receipt = arrival(data)
    queue_digest(kind="RECEIPT_BUYER", builder=build_buyer_receipt_digests)
    delivery = session.scalar(select(EmailOutbox))
    operation(data, receipt, "clarify")
    assert claim_delivery(delivery.id, {}) is None
    assert session.get(EmailOutbox, delivery.id).status == "SKIPPED"
    with patch("app.services.email_delivery.send_to_local_mailpit") as send:
        result = send_notification_digests_local()
        assert result["sent"] >= 1
        assert send_notification_digests_local()["sent"] == 0
    assert any("Depozitului" in call.args[0]["body"] for call in send.call_args_list)


def test_notifications_are_private_to_recipient_and_current_role(session, data):
    arrival(data)
    queue_digest(kind="RECEIPT_BUYER", builder=build_buyer_receipt_digests)
    client, _ = authorize(data["users"][Role.ACHIZITII])
    response = client.get("/api/notifications")
    assert response.status_code == 200 and response.json["total"] == 1
    assert response.headers["Cache-Control"] == "no-store"
    assert "content_hash" not in str(response.json)
    assert client.get("/api/notifications?recipient_user_id=1").status_code == 400
    warehouse, _ = authorize(data["users"][Role.DEPOZIT])
    assert warehouse.get("/api/notifications").json["total"] == 0
    admin, _ = authorize(data["users"][Role.ADMIN])
    assert admin.get("/api/notifications").status_code == 403
    user = session.get(User, data["users"][Role.ACHIZITII])
    user.role = Role.DEPOZIT
    session.commit()
    changed, _ = authorize(user.id)
    assert changed.get("/api/notifications").json["total"] == 0


def test_drafts_and_missing_active_teams_are_handled(session, data):
    arrival(data, confirmed=False)
    assert build_buyer_receipt_digests()["messages"] == []
    arrival(data)
    session.get(User, data["users"][Role.ACHIZITII]).is_active = False
    session.commit()
    digest = build_buyer_receipt_digests()
    assert digest["messages"] == [] and digest["skipped_items"] == 1


def test_configured_smtp_uses_separate_outbox_and_never_local_transport(session, data, monkeypatch):
    arrival(data)
    for key, value in {"MAIL_TRANSPORT": "SMTP", "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_SECURITY": "STARTTLS",
                       "SMTP_FROM_EMAIL": "sender@example.com", "SMTP_USERNAME": "", "SMTP_PASSWORD": ""}.items():
        monkeypatch.setitem(current_app.config, key, value)
    with patch("app.services.email_delivery.send_email") as smtp, patch("app.services.email_delivery.send_to_local_mailpit") as local:
        first = send_notification_digests()
        assert first["sent"] >= 1
        assert send_notification_digests()["sent"] == 0
        assert all(call.kwargs["transport"] == "SMTP" for call in smtp.call_args_list)
        local.assert_not_called()
    assert set(session.scalars(select(EmailOutbox.transport)).all()) == {"SMTP"}


def test_interrupted_claim_becomes_unknown_and_is_not_resent(session, data):
    arrival(data)
    digest = build_buyer_receipt_digests()
    queue_digest(kind="RECEIPT_BUYER", builder=build_buyer_receipt_digests)
    delivery = session.scalar(select(EmailOutbox))
    claim = claim_delivery(delivery.id, {message["recipient_user_id"]: message for message in digest["messages"]})
    attempt = session.get(EmailAttempt, claim["attempt_id"])
    attempt.started_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    session.commit()
    recover_stale_deliveries("LOCAL_MAILPIT")
    assert session.get(EmailOutbox, delivery.id).status == "UNKNOWN"
    assert session.get(EmailAttempt, attempt.id).error_code == "WORKER_INTERRUPTED"
    assert claim_delivery(delivery.id, {message["recipient_user_id"]: message for message in digest["messages"]}) is None


def test_worker_recovers_an_interrupted_claim_even_after_the_daily_digest(session, data, monkeypatch):
    from app.services import notification_worker as worker

    arrival(data)
    digest = build_buyer_receipt_digests()
    queue_digest(kind="RECEIPT_BUYER", builder=build_buyer_receipt_digests)
    delivery = session.scalar(select(EmailOutbox))
    claim = claim_delivery(delivery.id, {message["recipient_user_id"]: message for message in digest["messages"]})
    session.get(EmailAttempt, claim["attempt_id"]).started_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    session.commit()
    now = datetime(2026, 10, 21, 12)
    monkeypatch.setattr(worker, "bucharest_now", lambda: now)
    with patch.object(worker, "send_notification_digests") as send:
        assert worker.run_notification_tick(last_completed_date=now.date())["ran"] is False
        send.assert_not_called()
    assert session.get(EmailOutbox, delivery.id).status == "UNKNOWN"


@pytest.mark.parametrize("change", ["role", "active", "email"])
def test_recipient_is_rechecked_before_receipt_email_claim(session, data, change):
    arrival(data)
    digest = build_buyer_receipt_digests()
    queue_digest(kind="RECEIPT_BUYER", builder=build_buyer_receipt_digests)
    delivery = session.scalar(select(EmailOutbox))
    user = session.get(User, delivery.recipient_user_id)
    if change == "role":
        user.role = Role.DEPOZIT
    elif change == "active":
        user.is_active = False
    else:
        user.email = "changed@example.com"
    session.commit()
    assert claim_delivery(delivery.id, {message["recipient_user_id"]: message for message in digest["messages"]}) is None
    assert session.get(EmailOutbox, delivery.id).status == "SKIPPED"


def test_receipt_digest_is_received_once_by_real_local_mailpit(session, data):
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import urlopen
    from uuid import uuid4
    from app.services.email_delivery import send_receipt_digests_local

    if os.getenv("RUN_MAILPIT_TESTS") != "1":
        pytest.skip("Activeaza RUN_MAILPIT_TESTS=1 cu Mailpit de test pornit prin profilul Docker tests.")
    receipt = arrival(data)
    recipient = f"receipt-{uuid4().hex}@example.com"
    session.get(User, data["users"][Role.ACHIZITII]).email = recipient
    session.commit()
    assert send_receipt_digests_local(kind="RECEIPT_BUYER", builder=build_buyer_receipt_digests)["sent"] == 1
    assert send_receipt_digests_local(kind="RECEIPT_BUYER", builder=build_buyer_receipt_digests)["sent"] == 0
    from mailpit_config import mailpit_test_ui_port
    port = mailpit_test_ui_port()
    with urlopen(f"http://127.0.0.1:{port}/api/v1/search?{urlencode({'query': 'to:' + recipient})}", timeout=5) as response:
        messages = json.load(response)["messages"]
    assert len(messages) == 1
    with urlopen(f"http://127.0.0.1:{port}/api/v1/message/{messages[0]['ID']}", timeout=5) as response:
        message = json.load(response)
    assert receipt["number"] in message["Text"] and "10.000 BUC" in message["Text"]
    assert message["Subject"].startswith("[TEST] Ruris - clarificari receptii")
    buyer, _ = authorize(data["users"][Role.ACHIZITII])
    assert receipt["id"] in {item["id"] for item in buyer.get("/api/receipts/pending").json["receipts"]}
    journal = buyer.get("/api/notifications").json["notifications"]
    assert len(journal) == 1 and journal[0]["status"] == "SENT"
    assert receipt["number"] in journal[0]["body"]
    receipt = operation(data, receipt, "clarify").json["receipt"]
    receipt = operation(data, receipt, "resolve", quantity="10").json["receipt"]
    assert buyer.get("/api/receipts/pending").json["total"] == 0
    assert buyer.get("/api/notifications").json["total"] == 1
