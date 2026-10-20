import smtplib
from unittest.mock import patch

from flask import current_app
import pytest

from app.services.mail import LocalEmailDeliveryError, send_to_local_mailpit


@pytest.fixture
def app_context():
    from flask import Flask

    app = Flask(__name__)
    app.config["MAILPIT_SMTP_PORT"] = "1025"
    with app.app_context():
        yield app


def message(**changes):
    return {"to": "buyer@example.com", "subject": "Sumar întârziere", "body": "Marfă restantă: 7.000 BUC", **changes}


def test_transport_uses_only_loopback_and_builds_email_headers(app_context):
    with patch("app.services.mail.smtplib.SMTP") as smtp:
        connection = smtp.return_value.__enter__.return_value
        connection.send_message.return_value = {}
        send_to_local_mailpit(message())
    smtp.assert_called_once_with("127.0.0.1", 1025, timeout=5)
    email = connection.send_message.call_args.args[0]
    assert email["From"] == "ruris@example.test"
    assert email["To"] == "buyer@example.com"
    assert email["Subject"] == "Sumar întârziere"
    assert "Marfă restantă" in email.get_content()
    assert connection.send_message.call_args.kwargs["to_addrs"] == ["buyer@example.com"]


@pytest.mark.parametrize("error", [ConnectionRefusedError("private detail"), TimeoutError("private detail"),
                                  smtplib.SMTPException("private detail")])
def test_smtp_errors_are_sanitized(app_context, error):
    with patch("app.services.mail.smtplib.SMTP", side_effect=error):
        with pytest.raises(LocalEmailDeliveryError) as result:
            send_to_local_mailpit(message())
    assert "Mailpit" in str(result.value)
    assert "private detail" not in str(result.value)


@pytest.mark.parametrize("port", ["x", "0", "65536", None])
def test_invalid_port_never_connects(app_context, port):
    current_app.config["MAILPIT_SMTP_PORT"] = port
    with patch("app.services.mail.smtplib.SMTP") as smtp:
        with pytest.raises(LocalEmailDeliveryError):
            send_to_local_mailpit(message())
    smtp.assert_not_called()


def test_header_injection_never_connects(app_context):
    with patch("app.services.mail.smtplib.SMTP") as smtp:
        with pytest.raises(LocalEmailDeliveryError):
            send_to_local_mailpit(message(subject="Sumar\nBcc: other@example.com"))
    smtp.assert_not_called()


def test_connection_loss_after_submission_is_uncertain(app_context):
    with patch("app.services.mail.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.side_effect = smtplib.SMTPServerDisconnected("private")
        with pytest.raises(LocalEmailDeliveryError) as result:
            send_to_local_mailpit(message())
    assert result.value.delivery_unknown is True


def test_explicit_smtp_rejection_is_safe_to_retry(app_context):
    with patch("app.services.mail.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.side_effect = smtplib.SMTPDataError(550, b"rejected")
        with pytest.raises(LocalEmailDeliveryError) as result:
            send_to_local_mailpit(message())
    assert result.value.delivery_unknown is False
