from datetime import date, datetime
from unittest.mock import Mock, patch

from flask import Flask, current_app
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services import notification_worker as worker


@pytest.fixture
def worker_app(monkeypatch):
    app = Flask(__name__)
    app.config.update(EMAIL_DAILY_TIME="08:00", EMAIL_RETRY_SECONDS="300")
    monkeypatch.setattr(worker.db, "session", Mock())
    with app.app_context():
        yield app


def result(*, states=None, retryable=0):
    return {"as_of": "2026-10-20", "queued": 1, "skipped_items": 0,
            "sent": 1, "states": states or {"SENT": 1}, "retryable": retryable}


@pytest.mark.parametrize("clock,due", [("07:59:59", False), ("08:00:00", True), ("11:30:00", True)])
def test_daily_threshold_and_catchup(worker_app, monkeypatch, clock, due):
    monkeypatch.setattr(worker, "bucharest_now", lambda: datetime.fromisoformat(f"2026-10-20T{clock}"))
    with patch.object(worker, "send_overdue_digests_local", return_value=result()) as send:
        tick = worker.run_notification_tick()
    assert tick["ran"] is due
    assert send.call_count == int(due)
    if due:
        send.assert_called_once_with(retry_delay_seconds=300)
        assert tick["last_completed_date"] == date(2026, 10, 20)
    worker.db.session.rollback.assert_called_once()


def test_completed_day_is_skipped_and_next_day_runs(worker_app, monkeypatch):
    monkeypatch.setattr(worker, "bucharest_now", lambda: datetime(2026, 10, 20, 12))
    with patch.object(worker, "send_overdue_digests_local", return_value=result()) as send:
        assert worker.run_notification_tick(last_completed_date=date(2026, 10, 20))["ran"] is False
        assert worker.run_notification_tick(last_completed_date=date(2026, 10, 19))["ran"] is True
    send.assert_called_once()


def test_retryable_failure_keeps_day_open(worker_app, monkeypatch):
    monkeypatch.setattr(worker, "bucharest_now", lambda: datetime(2026, 10, 20, 8))
    with patch.object(worker, "send_overdue_digests_local", return_value=result(states={"FAILED": 1}, retryable=1)):
        assert worker.run_notification_tick()["last_completed_date"] is None


@pytest.mark.parametrize("status", ["UNKNOWN", "SENDING", "FAILED", "SKIPPED"])
def test_terminal_or_uncertain_messages_do_not_schedule_blind_retries(worker_app, monkeypatch, status):
    monkeypatch.setattr(worker, "bucharest_now", lambda: datetime(2026, 10, 20, 8))
    with patch.object(worker, "send_overdue_digests_local", return_value=result(states={status: 1}, retryable=0)):
        assert worker.run_notification_tick()["last_completed_date"] == date(2026, 10, 20)


@pytest.mark.parametrize("key,value", [
    ("EMAIL_DAILY_TIME", "8:00"), ("EMAIL_DAILY_TIME", "24:00"), ("EMAIL_DAILY_TIME", "08:60"),
    ("EMAIL_DAILY_TIME", None), ("EMAIL_RETRY_SECONDS", "x"), ("EMAIL_RETRY_SECONDS", "59"),
    ("EMAIL_RETRY_SECONDS", "3601"), ("EMAIL_RETRY_SECONDS", None),
])
def test_invalid_worker_settings_fail_clearly(worker_app, key, value):
    current_app.config[key] = value
    with pytest.raises(ValueError, match=key):
        worker.worker_settings()


def test_database_failure_releases_transaction(worker_app, monkeypatch):
    monkeypatch.setattr(worker, "bucharest_now", lambda: datetime(2026, 10, 20, 8))
    with patch.object(worker, "send_overdue_digests_local", side_effect=SQLAlchemyError("test")):
        with pytest.raises(SQLAlchemyError):
            worker.run_notification_tick()
    worker.db.session.rollback.assert_called_once()


def test_worker_cli_once_does_not_sleep(session):
    tick = {"ran": False, "last_completed_date": None, "local_time": "2026-10-20T07:59:00"}
    with patch("app.cli.run_notification_tick", return_value=tick) as run, patch("app.cli.Event") as event:
        output = current_app.test_cli_runner().invoke(args=["run-notification-worker", "--once"])
    assert output.exit_code == 0
    assert "Nu este necesara procesarea acum" in output.output
    run.assert_called_once()
    event.return_value.wait.assert_not_called()


def test_worker_cli_recovers_from_database_failure_on_next_check(session):
    tick = {"ran": True, "last_completed_date": date(2026, 10, 20), "local_time": "2026-10-20T08:01:00", **result()}
    with patch("app.cli.run_notification_tick", side_effect=[SQLAlchemyError("private detail"), tick]) as run, patch("app.cli.Event") as event:
        event.return_value.wait.side_effect = [False, True]
        output = current_app.test_cli_runner().invoke(args=["run-notification-worker", "--poll-seconds", "1"])
    assert output.exit_code == 0
    assert run.call_count == 2
    assert "Verificarea a esuat" in output.output
    assert "acceptate: 1" in output.output
    assert "private detail" not in output.output


def test_worker_cli_once_reports_database_error(session):
    with patch("app.cli.run_notification_tick", side_effect=SQLAlchemyError("private detail")):
        output = current_app.test_cli_runner().invoke(args=["run-notification-worker", "--once"])
    assert output.exit_code != 0
    assert "private detail" not in output.output


@pytest.mark.parametrize("moment", ["2026-01-01T06:00:00+00:00", "2026-07-01T05:00:00+00:00"])
def test_worker_local_time_accounts_for_winter_and_summer(session, moment):
    assert worker.bucharest_now(datetime.fromisoformat(moment)).hour == 8
