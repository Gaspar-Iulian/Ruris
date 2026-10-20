from datetime import date, datetime, timezone
from unittest.mock import patch

from flask import current_app
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models import AuditEvent, Product, PurchaseOrder, PurchaseOrderItem, Role, StockMovement, Supplier, User
from app.services.notifications import build_overdue_digests


@pytest.fixture
def catalog(session, monkeypatch):
    monkeypatch.setattr("app.services.notifications.bucharest_date", lambda: date(2026, 10, 20))
    users = [User(name=f"Responsabil {index}", email=f"buyer-{index}@example.com", role=Role.ACHIZITII,
                  password_hash="private-hash-never-include", token_version=1, is_active=True) for index in range(2)]
    supplier = Supplier(name="Furnizor", tax_country="RO", tax_id="123")
    product = Product(sku="P1", name="Produs", unit="KG")
    session.add_all([*users, supplier, product])
    session.flush()
    return {"users": users, "supplier": supplier, "product": product}


def add_order(session, catalog, owner, *, description="Produs intarziat", deadline=date(2026, 10, 18), status="CONFIRMED", count=1):
    order = PurchaseOrder(supplier_id=catalog["supplier"].id, currency="RON", status=status, owner_id=owner.id,
                          created_by_id=owner.id, confirmed_at=datetime.now(timezone.utc) if status == "CONFIRMED" else None)
    for line in range(1, count + 1):
        order.items.append(PurchaseOrderItem(line_number=line, product_id=catalog["product"].id, description=description,
                                             unit="KG", quantity=5, unit_price=777, vat_rate=0, expected_date=deadline))
    session.add(order)
    session.flush()
    return order


def test_each_owner_receives_only_their_overdue_orders(session, catalog):
    first, second = catalog["users"]
    add_order(session, catalog, first, description="Marfa pentru primul", deadline=date(2026, 10, 18))
    add_order(session, catalog, first, description="Alta marfa pentru primul", deadline=date(2026, 10, 17))
    add_order(session, catalog, second, description="Marfa pentru al doilea")
    emails = [first.email, second.email]
    session.commit()
    digest = build_overdue_digests()
    assert digest["as_of"] == "2026-10-20"
    assert digest["timezone"] == "Europe/Bucharest"
    assert digest["skipped_items"] == 0
    assert [message["to"] for message in digest["messages"]] == emails
    first_message, second_message = digest["messages"]
    assert first_message["item_count"] == 2
    assert second_message["item_count"] == 1
    assert "Marfa pentru primul" in first_message["body"]
    assert "Marfa pentru al doilea" not in first_message["body"]
    assert "Marfa pentru primul" not in second_message["body"]
    assert first_message["body"].index("Alta marfa pentru primul") < first_message["body"].index("Marfa pentru primul")
    assert "5.000 KG" in first_message["body"]
    assert "intarziere: 3 zile" in first_message["body"]
    assert "2026-10-20" in first_message["subject"]
    assert all("777" not in message["body"] and "private-hash" not in message["body"] for message in digest["messages"])


@pytest.mark.parametrize("ineligible", ["inactive", "admin", "warehouse", "accounting"])
def test_ineligible_owner_is_skipped_and_reported(session, catalog, ineligible):
    owner = catalog["users"][0]
    if ineligible == "inactive":
        owner.is_active = False
    else:
        owner.role = {"admin": Role.ADMIN, "warehouse": Role.DEPOZIT, "accounting": Role.CONTABILITATE}[ineligible]
    add_order(session, catalog, owner)
    session.commit()
    digest = build_overdue_digests()
    assert digest["messages"] == []
    assert digest["skipped_items"] == 1
    result = current_app.test_cli_runner().invoke(args=["preview-overdue-emails"])
    assert result.exit_code == 0
    assert "Pozitii fara responsabil activ cu rolul ACHIZITII: 1" in result.output


def test_no_messages_for_empty_or_non_overdue_orders(session, catalog):
    owner = catalog["users"][0]
    add_order(session, catalog, owner, status="DRAFT")
    add_order(session, catalog, owner, status="CANCELLED")
    add_order(session, catalog, owner, status="CLOSED")
    add_order(session, catalog, owner, deadline=date(2026, 10, 20))
    add_order(session, catalog, owner, deadline=date(2026, 10, 21))
    session.commit()
    assert build_overdue_digests()["messages"] == []
    result = current_app.test_cli_runner().invoke(args=["preview-overdue-emails"])
    assert result.exit_code == 0
    assert "Mesaje pregatite: 0" in result.output
    assert "Catre:" not in result.output


def test_digest_includes_more_than_default_api_page(session, catalog):
    add_order(session, catalog, catalog["users"][0], count=21)
    session.commit()
    digest = build_overdue_digests()
    assert len(digest["messages"]) == 1
    assert digest["messages"][0]["item_count"] == 21
    assert "pozitia 21:" in digest["messages"][0]["body"]


def test_cli_preview_is_read_only_and_outputs_recipient_subject_and_body(session, catalog):
    add_order(session, catalog, catalog["users"][0])
    session.commit()
    audit_count = session.scalar(select(func.count()).select_from(AuditEvent))
    result = current_app.test_cli_runner().invoke(args=["preview-overdue-emails"])
    assert result.exit_code == 0
    assert "Nu sunt trimise emailuri" in result.output
    assert "Catre: buyer-0@example.com" in result.output
    assert "Subiect: Ruris - sumar intarzieri - 2026-10-20" in result.output
    assert "Produs intarziat" in result.output
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_count
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert session.scalar(select(PurchaseOrder.version)) == 1


def test_cli_database_error_is_sanitized(session):
    with patch("app.cli.build_overdue_digests", side_effect=SQLAlchemyError("private connection detail")):
        result = current_app.test_cli_runner().invoke(args=["preview-overdue-emails"])
    assert result.exit_code != 0
    assert "Sumarul nu a putut fi generat" in result.output
    assert "private connection detail" not in result.output


def test_local_send_cli_uses_generated_digests(session, catalog):
    add_order(session, catalog, catalog["users"][0])
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit") as send:
        result = current_app.test_cli_runner().invoke(args=["send-overdue-emails-local"])
    assert result.exit_code == 0
    assert "Mesaje acceptate de Mailpit local: 1" in result.output
    assert send.call_args.args[0]["to"] == "buyer-0@example.com"
    assert "Produs intarziat" in send.call_args.args[0]["body"]


def test_local_send_cli_reports_partial_failure(session, catalog):
    from app.services.mail import LocalEmailDeliveryError

    for user in catalog["users"]:
        add_order(session, catalog, user)
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit", side_effect=[None, LocalEmailDeliveryError("Mailpit indisponibil")]):
        result = current_app.test_cli_runner().invoke(args=["send-overdue-emails-local"])
    assert result.exit_code != 0
    assert "Mesaje acceptate anterior in aceasta rulare: 1" in result.output


def test_demonstration_email_uses_relative_deadline_and_no_database_writes(session, catalog):
    from app.services.notifications import build_test_overdue_message

    session.commit()
    before = session.scalar(select(func.count()).select_from(PurchaseOrder))
    message = build_test_overdue_message()
    assert message["subject"] == "[TEST] Ruris - sumar intarzieri - 2026-10-20"
    assert "2026-10-19" in message["body"]
    assert "7.000 BUC" in message["body"]
    assert message["to"] == "achizitii@example.com"
    with patch("app.cli.send_to_local_mailpit") as send:
        result = current_app.test_cli_runner().invoke(args=["send-test-email"])
    assert result.exit_code == 0
    send.assert_called_once()
    assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == before


def test_overdue_digest_reaches_mailpit_via_smtp(session, catalog):
    import json
    import os
    from urllib.parse import urlencode
    from urllib.request import urlopen
    from uuid import uuid4

    if os.getenv("RUN_MAILPIT_TESTS") != "1":
        pytest.skip("Activeaza RUN_MAILPIT_TESTS=1 cu Mailpit local pornit.")
    recipient = f"mailpit-{uuid4().hex}@example.com"
    catalog["users"][0].email = recipient
    add_order(session, catalog, catalog["users"][0], description="Produs verificat prin SMTP")
    session.commit()
    audit_count = session.scalar(select(func.count()).select_from(AuditEvent))
    result = current_app.test_cli_runner().invoke(args=["send-overdue-emails-local"])
    assert result.exit_code == 0, result.output
    repeated = current_app.test_cli_runner().invoke(args=["send-overdue-emails-local"])
    assert repeated.exit_code == 0
    assert "Mesaje acceptate de Mailpit local: 0" in repeated.output
    ui_port = int(os.getenv("MAILPIT_UI_PORT", "8025"))
    query = urlencode({"query": f"to:{recipient}"})
    with urlopen(f"http://127.0.0.1:{ui_port}/api/v1/search?{query}", timeout=5) as response:
        captured = json.load(response)
    assert len(captured["messages"]) == 1
    summary = captured["messages"][0]
    assert summary["Subject"] == "Ruris - sumar intarzieri - 2026-10-20"
    assert summary["To"][0]["Address"] == recipient
    with urlopen(f"http://127.0.0.1:{ui_port}/api/v1/message/{summary['ID']}", timeout=5) as response:
        full_message = json.load(response)
    assert "Produs verificat prin SMTP" in full_message["Text"]
    assert "5.000 KG" in full_message["Text"]
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_count + 3


def test_daily_digest_is_queued_and_sent_only_once(session, catalog):
    from app.models import EmailAttempt, EmailOutbox
    from app.services.email_delivery import send_overdue_digests_local

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit") as send:
        first = send_overdue_digests_local()
        second = send_overdue_digests_local()
    assert first["sent"] == first["queued"] == 1
    assert second["sent"] == second["queued"] == 0
    send.assert_called_once()
    delivery = session.scalar(select(EmailOutbox))
    assert delivery.status == "SENT"
    assert delivery.sent_at is not None
    assert delivery.attempt_count == 1
    assert session.scalar(select(func.count()).select_from(EmailAttempt)) == 1
    assert [event.action for event in session.scalars(select(AuditEvent).where(AuditEvent.entity_type == "email_outbox").order_by(AuditEvent.id))] == ["ENQUEUE", "START", "SENT"]
    journal = current_app.test_cli_runner().invoke(args=["list-email-deliveries"])
    assert journal.exit_code == 0
    assert "SENT | incercari 1" in journal.output
    assert delivery.body not in journal.output


def test_definite_failure_can_be_retried_with_same_message_id(session, catalog):
    from app.models import EmailAttempt, EmailOutbox
    from app.services.email_delivery import send_overdue_digests_local
    from app.services.mail import LocalEmailDeliveryError

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit", side_effect=LocalEmailDeliveryError("Connection failed")) as first:
        assert send_overdue_digests_local()["states"] == {"FAILED": 1}
    with patch("app.services.email_delivery.send_to_local_mailpit") as retry:
        assert send_overdue_digests_local()["sent"] == 1
    assert first.call_args.args[0]["message_id"] == retry.call_args.args[0]["message_id"]
    assert session.scalar(select(EmailOutbox)).attempt_count == 2
    assert [attempt.status for attempt in session.scalars(select(EmailAttempt).order_by(EmailAttempt.id))] == ["FAILED", "SENT"]


def test_unknown_result_is_not_retried(session, catalog):
    from app.models import EmailOutbox
    from app.services.email_delivery import send_overdue_digests_local
    from app.services.mail import LocalEmailDeliveryError

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit", side_effect=LocalEmailDeliveryError("Timeout after send", delivery_unknown=True)) as send:
        assert send_overdue_digests_local()["states"] == {"UNKNOWN": 1}
        assert send_overdue_digests_local()["sent"] == 0
    send.assert_called_once()
    delivery = session.scalar(select(EmailOutbox))
    assert delivery.last_error == "SMTP_RESULT_UNKNOWN"
    assert delivery.attempt_count == 1


def test_retries_stop_after_three_definite_failures(session, catalog):
    from app.models import EmailAttempt
    from app.services.email_delivery import send_overdue_digests_local
    from app.services.mail import LocalEmailDeliveryError

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit", side_effect=LocalEmailDeliveryError("Offline")) as send:
        for _ in range(4):
            send_overdue_digests_local()
    assert send.call_count == 3
    assert session.scalar(select(func.count()).select_from(EmailAttempt)) == 3


@pytest.mark.parametrize("change", ["inactive", "role", "email", "content"])
def test_stale_or_ineligible_queued_message_is_skipped(session, catalog, change):
    from app.models import EmailOutbox
    from app.services.email_delivery import queue_overdue_emails, send_overdue_digests_local

    user = catalog["users"][0]
    order = add_order(session, catalog, user)
    session.commit()
    assert queue_overdue_emails()["queued"] == 1
    if change == "inactive":
        user.is_active = False
    elif change == "role":
        user.role = Role.DEPOZIT
    elif change == "email":
        user.email = "changed@example.com"
    else:
        order.items[0].quantity = 8
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit") as send:
        result = send_overdue_digests_local()
    send.assert_not_called()
    assert result["states"] == {"SKIPPED": 1}
    assert session.scalar(select(EmailOutbox)).attempt_count == 0


def test_new_business_day_allows_new_digest(session, catalog, monkeypatch):
    from app.services.email_delivery import send_overdue_digests_local

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    with patch("app.services.email_delivery.send_to_local_mailpit") as send:
        assert send_overdue_digests_local()["sent"] == 1
        monkeypatch.setattr("app.services.notifications.bucharest_date", lambda: date(2026, 10, 21))
        assert send_overdue_digests_local()["sent"] == 1
    assert send.call_count == 2


def test_queue_audit_failure_prevents_smtp_and_rolls_back_outbox(session, catalog):
    from app.models import EmailOutbox
    from app.services.email_delivery import send_overdue_digests_local

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    with patch("app.services.email_delivery.record_audit", side_effect=SQLAlchemyError("test")), patch("app.services.email_delivery.send_to_local_mailpit") as send:
        with pytest.raises(SQLAlchemyError):
            send_overdue_digests_local()
    send.assert_not_called()
    assert session.scalar(select(func.count()).select_from(EmailOutbox)) == 0


def test_failure_after_smtp_leaves_durable_sending_state_without_resend(session, catalog):
    from app.models import EmailOutbox
    from app.services.audit import record_audit
    from app.services.email_delivery import send_overdue_digests_local

    add_order(session, catalog, catalog["users"][0])
    session.commit()

    def fail_final_audit(**kwargs):
        if kwargs["action"] == "SENT":
            raise SQLAlchemyError("Database failed after SMTP")
        return record_audit(**kwargs)

    with patch("app.services.email_delivery.record_audit", side_effect=fail_final_audit), patch("app.services.email_delivery.send_to_local_mailpit") as send:
        with pytest.raises(SQLAlchemyError):
            send_overdue_digests_local()
    send.assert_called_once()
    assert session.scalar(select(EmailOutbox)).status == "SENDING"
    with patch("app.services.email_delivery.send_to_local_mailpit") as repeated:
        assert send_overdue_digests_local()["sent"] == 0
    repeated.assert_not_called()


def test_two_claims_cannot_take_the_same_message(session, catalog):
    from app.services.email_delivery import claim_delivery, queue_overdue_emails
    from app.services.notifications import build_overdue_digests
    from app.models import EmailOutbox

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    queue_overdue_emails()
    delivery_id = session.scalar(select(EmailOutbox.id))
    fresh = {message["recipient_user_id"]: message for message in build_overdue_digests()["messages"]}
    first = claim_delivery(delivery_id, fresh)
    second = claim_delivery(delivery_id, fresh)
    assert first is not None
    assert second is None


def test_daily_key_is_enforced_by_database(session, catalog):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy import text
    from app.services.email_delivery import queue_overdue_emails

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    queue_overdue_emails()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.execute(text("INSERT INTO email_outbox (kind, transport, as_of, recipient_user_id, recipient_email, subject, body, content_hash) "
                                 "SELECT kind, transport, as_of, recipient_user_id, recipient_email, subject, body, content_hash FROM email_outbox"))


def test_retry_deadline_is_persisted_and_respected_after_reload(session, catalog):
    from datetime import timedelta
    from app.models import EmailOutbox
    from app.services.email_delivery import send_overdue_digests_local
    from app.services.mail import LocalEmailDeliveryError

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    initial_time = datetime(2026, 10, 20, 5, tzinfo=timezone.utc)
    with patch("app.services.email_delivery.datetime") as clock:
        clock.now.return_value = initial_time
        with patch("app.services.email_delivery.send_to_local_mailpit", side_effect=LocalEmailDeliveryError("Offline")):
            first = send_overdue_digests_local(retry_delay_seconds=300)
        assert first["retryable"] == 1
        session.expire_all()
        assert session.scalar(select(EmailOutbox)).next_attempt_at == initial_time + timedelta(seconds=300)
        clock.now.return_value = initial_time + timedelta(seconds=299)
        with patch("app.services.email_delivery.send_to_local_mailpit") as send:
            assert send_overdue_digests_local(retry_delay_seconds=300)["sent"] == 0
        send.assert_not_called()
        clock.now.return_value = initial_time + timedelta(seconds=300)
        with patch("app.services.email_delivery.send_to_local_mailpit") as send:
            assert send_overdue_digests_local(retry_delay_seconds=300)["sent"] == 1
        send.assert_called_once()
    assert session.scalar(select(EmailOutbox)).next_attempt_at is None


def test_restarted_worker_does_not_resend_completed_daily_digest(session, catalog, monkeypatch):
    from app.services.notification_worker import run_notification_tick

    add_order(session, catalog, catalog["users"][0])
    session.commit()
    monkeypatch.setattr("app.services.notification_worker.bucharest_now", lambda: datetime(2026, 10, 20, 9))
    with patch("app.services.email_delivery.send_to_local_mailpit") as send:
        assert run_notification_tick()["sent"] == 1
        assert run_notification_tick()["sent"] == 0
    send.assert_called_once()
