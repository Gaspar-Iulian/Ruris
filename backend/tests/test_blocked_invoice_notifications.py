from datetime import date, datetime, timezone
from unittest.mock import patch

from flask import current_app
import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, EmailOutbox, Invoice, InvoiceIssue, Role, Supplier, User
from app.services.email_delivery import claim_delivery, queue_blocked_invoice_emails, send_blocked_invoice_digests_local, send_notification_digests_local, send_overdue_digests_local
from app.services.mail import LocalEmailDeliveryError
from app.services.notifications import build_blocked_invoice_digests


@pytest.fixture
def catalog(session, monkeypatch):
    monkeypatch.setattr("app.services.notifications.bucharest_date", lambda: date(2026, 10, 20))
    users = [User(name=f"Contabil {index}", email=f"accountant-{index}@example.com", role=Role.CONTABILITATE,
                  password_hash="private-hash", token_version=1, is_active=True) for index in range(2)]
    other = [User(name=role.value, email=f"other-{role.value}@example.com", role=role,
                  password_hash="private-hash", token_version=1, is_active=True) for role in (Role.ADMIN, Role.ACHIZITII, Role.DEPOZIT)]
    supplier = Supplier(name="Furnizor test", tax_country="RO", tax_id="123")
    session.add_all([*users, *other, supplier])
    session.flush()
    return {"users": users, "supplier": supplier}


def add_invoice(session, catalog, number="001", *, status="BLOCKED", code="NO_ITEMS", resolution=None):
    now = datetime.now(timezone.utc)
    values = {}
    if status in ("APPROVED", "PAID"):
        values.update(approved_by_id=catalog["users"][0].id, approved_at=now, exchange_rate_value=1,
                      exchange_rate_source="IDENTITY", exchange_rate_date=date(2026, 10, 20), total_ron="12345.67")
    if status == "PAID":
        values.update(paid_by_id=catalog["users"][0].id, paid_at=now, payment_reference="OP-1")
    invoice = Invoice(supplier_id=catalog["supplier"].id, series="AB", number=number, invoice_date=date(2026, 10, 20),
        due_date=date(2026, 11, 20), currency="RON", status=status, net_amount="12345.67", vat_amount=0,
        total_amount="12345.67", created_by_id=catalog["users"][0].id, **values)
    session.add(invoice)
    session.flush()
    issue = InvoiceIssue(invoice_id=invoice.id, code=code, details="Lipseste justificarea marfii", responsible_role="CONTABILITATE",
                         resolution=resolution, resolved_at=now if resolution else None)
    session.add(issue)
    session.flush()
    return invoice, issue


def test_only_accountants_receive_open_issues_without_financial_details(session, catalog):
    add_invoice(session, catalog)
    add_invoice(session, catalog, "002", code="TERMS_MISMATCH")
    session.commit()
    digest = build_blocked_invoice_digests()
    assert len(digest["messages"]) == 2
    for message in digest["messages"]:
        assert message["to"].startswith("accountant-")
        assert message["item_count"] == 2
        assert "AB 001" in message["body"] and "AB 002" in message["body"]
        assert "NO_ITEMS" in message["body"] and "TERMS_MISMATCH" in message["body"]
        assert "Furnizor test" in message["body"]
        assert "12345.67" not in message["body"] and "private-hash" not in message["body"]


@pytest.mark.parametrize("status", ["DRAFT", "VERIFIED", "APPROVED", "PAID"])
def test_other_invoice_states_are_excluded(session, catalog, status):
    add_invoice(session, catalog, status=status)
    session.commit()
    assert build_blocked_invoice_digests()["messages"] == []


@pytest.mark.parametrize("resolution", ["RESOLVED", "SUPERSEDED"])
def test_closed_issues_are_excluded(session, catalog, resolution):
    add_invoice(session, catalog, resolution=resolution)
    session.commit()
    assert build_blocked_invoice_digests()["messages"] == []


def test_inactive_or_changed_accountants_not_used_and_missing_team_reported(session, catalog):
    add_invoice(session, catalog)
    catalog["users"][0].is_active = False
    catalog["users"][1].role = Role.ACHIZITII
    session.commit()
    digest = build_blocked_invoice_digests()
    assert digest["messages"] == []
    assert digest["skipped_items"] == 1


def test_more_than_one_page_of_issues_is_included(session, catalog):
    for index in range(25):
        add_invoice(session, catalog, str(index))
    session.commit()
    assert all(message["item_count"] == 25 for message in build_blocked_invoice_digests()["messages"])


def test_dedup_delivery_and_overdue_channel_isolation(session, catalog):
    add_invoice(session, catalog)
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit") as send:
        result = send_blocked_invoice_digests_local()
        assert result["sent"] == 2
        assert send_blocked_invoice_digests_local()["sent"] == 0
        assert send_overdue_digests_local()["states"] == {}
    assert send.call_count == 2
    assert session.scalar(select(func.count()).select_from(EmailOutbox)) == 2
    events = session.scalars(select(AuditEvent).where(AuditEvent.entity_type == "email_outbox")).all()
    assert len(events) == 6
    assert all(event.actor_process == "blocked_invoice_email_local" for event in events)
    journal = current_app.test_cli_runner().invoke(args=["list-email-deliveries"])
    assert journal.exit_code == 0
    assert "BLOCKED_INVOICES" in journal.output


@pytest.mark.parametrize("change", ["status", "role", "email", "active", "resolved"])
def test_stale_or_unauthorized_delivery_is_skipped(session, catalog, change):
    invoice, issue = add_invoice(session, catalog)
    session.commit()
    queue_blocked_invoice_emails()
    user = catalog["users"][0]
    delivery_id = session.scalar(select(EmailOutbox.id).where(EmailOutbox.recipient_user_id == user.id))
    if change == "status":
        invoice.status = "DRAFT"
    elif change == "role":
        user.role = Role.ACHIZITII
    elif change == "email":
        user.email = "new@example.com"
    elif change == "active":
        user.is_active = False
    else:
        issue.resolved_at, issue.resolution = datetime.now(timezone.utc), "RESOLVED"
    session.commit()
    messages = {message["recipient_user_id"]: message for message in build_blocked_invoice_digests()["messages"]}
    assert claim_delivery(delivery_id, messages) is None
    assert session.get(EmailOutbox, delivery_id).status == "SKIPPED"


def test_failed_smtp_retries_then_stops(session, catalog):
    add_invoice(session, catalog)
    catalog["users"][1].is_active = False
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit", side_effect=LocalEmailDeliveryError("SMTP indisponibil")) as send:
        for _ in range(4):
            result = send_blocked_invoice_digests_local()
    assert send.call_count == 3
    assert result["retryable"] == 0


def test_unknown_smtp_result_is_not_retried(session, catalog):
    add_invoice(session, catalog)
    catalog["users"][1].is_active = False
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit", side_effect=LocalEmailDeliveryError("Timeout dupa trimitere", delivery_unknown=True)) as send:
        assert send_blocked_invoice_digests_local()["states"] == {"UNKNOWN": 1}
        assert send_blocked_invoice_digests_local()["sent"] == 0
    assert send.call_count == 1


def test_blocked_digest_is_captured_once_by_local_mailpit(session, catalog):
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import urlopen
    from uuid import uuid4

    if os.getenv("RUN_MAILPIT_TESTS") != "1":
        pytest.skip("Activeaza RUN_MAILPIT_TESTS=1 cu Mailpit local pornit.")
    add_invoice(session, catalog)
    recipient = f"blocked-{uuid4().hex}@example.com"
    catalog["users"][0].email = recipient
    catalog["users"][1].is_active = False
    session.commit()
    assert send_blocked_invoice_digests_local()["sent"] == 1
    assert send_blocked_invoice_digests_local()["sent"] == 0
    port = int(os.getenv("MAILPIT_UI_PORT", "8025"))
    with urlopen(f"http://127.0.0.1:{port}/api/v1/search?{urlencode({'query': 'to:' + recipient})}", timeout=5) as response:
        result = json.load(response)
    assert len(result["messages"]) == 1
    message_id = result["messages"][0]["ID"]
    with urlopen(f"http://127.0.0.1:{port}/api/v1/message/{message_id}", timeout=5) as response:
        message = json.load(response)
    assert "NO_ITEMS" in message["Text"]
    assert "AB 001" in message["Text"]


def test_worker_combines_retryable_counts_from_all_channels():
    overdue = {"as_of": "2026-10-20", "queued": 1, "sent": 1, "states": {"SENT": 1}, "retryable": 0, "skipped_items": 0}
    blocked = {**overdue, "sent": 0, "states": {"FAILED": 1}, "retryable": 1}
    empty = {**overdue, "queued": 0, "sent": 0, "states": {}}
    with patch("app.services.email_delivery.send_receipt_digests_local", return_value=empty) as receipts, patch(
        "app.services.email_delivery.send_overdue_digests_local", return_value=overdue) as first, patch(
        "app.services.email_delivery.send_blocked_invoice_digests_local", return_value=blocked) as second:
        result = send_notification_digests_local(retry_delay_seconds=300)
    assert result["retryable"] == 1 and result["queued"] == 2
    assert result["states"] == {"SENT": 1, "FAILED": 1}
    first.assert_called_once_with(retry_delay_seconds=300)
    second.assert_called_once_with(retry_delay_seconds=300)
    assert receipts.call_count == 2


def test_preview_cli_does_not_queue_or_send(session, catalog):
    add_invoice(session, catalog)
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit") as send:
        output = current_app.test_cli_runner().invoke(args=["preview-blocked-invoice-emails"])
    assert output.exit_code == 0
    assert "NO_ITEMS" in output.output
    send.assert_not_called()
    assert session.scalar(select(func.count()).select_from(EmailOutbox)) == 0
