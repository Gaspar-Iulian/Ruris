from flask import Flask
import pytest

from mailpit_config import configure_test_mailpit


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("MAILPIT_TEST_SMTP_PORT", "1026")
    monkeypatch.setenv("MAILPIT_TEST_UI_PORT", "8026")
    monkeypatch.setenv("MAILPIT_UI_PORT", "8025")
    app = Flask(__name__)
    app.config.update(MAILPIT_SMTP_PORT="1025", MAIL_TRANSPORT="SMTP", SMTP_HOST="external.example.com")
    return app


def test_automated_emails_use_a_separate_local_inbox_and_test_subject(settings):
    configure_test_mailpit(settings)
    assert settings.config["MAILPIT_SMTP_PORT"] == "1026"
    assert settings.config["MAILPIT_TEST_UI_PORT"] == 8026
    assert settings.config["MAIL_TRANSPORT"] == "LOCAL_MAILPIT"
    assert settings.config["MAILPIT_SMTP_HOST"] == "127.0.0.1"
    assert settings.config["MAIL_SUBJECT_PREFIX"] == "[TEST] "


@pytest.mark.parametrize("key,value", [("MAILPIT_TEST_SMTP_PORT", "1025"), ("MAILPIT_TEST_UI_PORT", "8025"),
    ("MAILPIT_TEST_SMTP_PORT", "8026"), ("MAILPIT_TEST_SMTP_PORT", "0"), ("MAILPIT_TEST_UI_PORT", "65536"),
    ("MAILPIT_TEST_SMTP_PORT", "bad")])
def test_shared_or_invalid_test_ports_are_rejected(settings, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError):
        configure_test_mailpit(settings)
