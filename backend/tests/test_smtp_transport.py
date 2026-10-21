import smtplib
from unittest.mock import patch

import pytest

from app.services.mail import LocalEmailDeliveryError, mail_settings, send_email, send_to_local_mailpit
from test_mail import app_context, message


@pytest.fixture
def smtp_app(app_context):
    app_context.config.update(MAIL_TRANSPORT="SMTP", SMTP_HOST="smtp.example.com", SMTP_PORT="587",
        SMTP_SECURITY="STARTTLS", SMTP_USERNAME="sender@example.com", SMTP_PASSWORD="private-password",
        SMTP_FROM_EMAIL="sender@example.com")
    return app_context


def test_starttls_and_authentication_precede_submission(smtp_app):
    with patch("app.services.mail.smtplib.SMTP") as smtp:
        connection = smtp.return_value.__enter__.return_value
        connection.send_message.return_value = {}
        send_email(message())
        assert [call[0] for call in connection.method_calls] == ["ehlo", "starttls", "ehlo", "login", "send_message"]
        connection.login.assert_called_once_with("sender@example.com", "private-password")
        assert connection.send_message.call_args.kwargs["from_addr"] == "sender@example.com"
    smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)


def test_ssl_uses_a_verified_context(smtp_app):
    smtp_app.config.update(SMTP_SECURITY="SSL", SMTP_PORT="465")
    with patch("app.services.mail.smtplib.SMTP_SSL") as smtp, patch("app.services.mail.smtplib.SMTP") as plain:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        send_email(message())
        assert smtp.call_args.kwargs["context"].check_hostname is True
        plain.assert_not_called()


@pytest.mark.parametrize("field,value", [("SMTP_HOST", ""), ("SMTP_HOST", "https://smtp.example.com"),
    ("SMTP_PORT", "0"), ("SMTP_SECURITY", "NONE"), ("SMTP_FROM_EMAIL", "not-email"),
    ("SMTP_PASSWORD", ""), ("MAIL_TRANSPORT", "OTHER")])
def test_invalid_smtp_settings_never_connect(smtp_app, field, value):
    smtp_app.config[field] = value
    with patch("app.services.mail.smtplib.SMTP") as smtp:
        with pytest.raises(LocalEmailDeliveryError):
            send_email(message())
        smtp.assert_not_called()


def test_local_commands_keep_using_mailpit_when_smtp_is_configured(smtp_app):
    with patch("app.services.mail.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        send_to_local_mailpit(message())
        smtp.assert_called_once_with("127.0.0.1", 1025, timeout=5)
        smtp.return_value.__enter__.return_value.login.assert_not_called()


@pytest.mark.parametrize("stage,unknown", [("starttls", False), ("login", False), ("send_message", True)])
def test_smtp_failures_hide_credentials_and_preserve_uncertainty(smtp_app, stage, unknown):
    with patch("app.services.mail.smtplib.SMTP") as smtp:
        connection = smtp.return_value.__enter__.return_value
        getattr(connection, stage).side_effect = smtplib.SMTPServerDisconnected("private-password")
        with pytest.raises(LocalEmailDeliveryError) as error:
            send_email(message())
    assert error.value.delivery_unknown is unknown
    assert "private-password" not in str(error.value)


def test_mailpit_host_can_use_the_docker_service_but_not_an_external_server(app_context):
    app_context.config["MAILPIT_SMTP_HOST"] = "mailpit"
    assert mail_settings()["host"] == "mailpit"
    app_context.config["MAILPIT_SMTP_HOST"] = "external.example.com"
    with pytest.raises(ValueError):
        mail_settings()
