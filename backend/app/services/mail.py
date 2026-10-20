from email.message import EmailMessage
import smtplib

from flask import current_app


class LocalEmailDeliveryError(RuntimeError):
    def __init__(self, message, *, delivery_unknown=False):
        super().__init__(message)
        self.delivery_unknown = delivery_unknown


def send_to_local_mailpit(message):
    try:
        port = int(current_app.config["MAILPIT_SMTP_PORT"])
        if not 1 <= port <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        raise LocalEmailDeliveryError("MAILPIT_SMTP_PORT trebuie sa fie intre 1 si 65535.") from None
    try:
        email = EmailMessage()
        email["From"] = "ruris@example.test"
        email["To"] = message["to"]
        email["Subject"] = message["subject"]
        if message.get("message_id"):
            email["Message-ID"] = message["message_id"]
        email.set_content(message["body"])
    except (ValueError, TypeError):
        raise LocalEmailDeliveryError("Mesajul contine campuri de email invalide.") from None
    submission_started = False
    try:
        with smtplib.SMTP("127.0.0.1", port, timeout=5) as smtp:
            submission_started = True
            refused = smtp.send_message(email, from_addr="ruris@example.test", to_addrs=[message["to"]])
            if refused:
                raise LocalEmailDeliveryError("Mailpit nu a acceptat destinatarul mesajului.")
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        raise LocalEmailDeliveryError("Mailpit a refuzat mesajul.") from None
    except (OSError, smtplib.SMTPException):
        raise LocalEmailDeliveryError("Mesajul nu a putut fi trimis catre Mailpit. Verifica serviciul Docker si portul SMTP local.",
                                      delivery_unknown=submission_started) from None
