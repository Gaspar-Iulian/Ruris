from email.message import EmailMessage
import smtplib
import ssl

from email_validator import EmailNotValidError, validate_email
from flask import current_app


class LocalEmailDeliveryError(RuntimeError):
    def __init__(self, message, *, delivery_unknown=False):
        super().__init__(message)
        self.delivery_unknown = delivery_unknown


def configured_transport():
    transport = current_app.config.get("MAIL_TRANSPORT", "LOCAL_MAILPIT")
    if transport not in ("LOCAL_MAILPIT", "SMTP"):
        raise ValueError("MAIL_TRANSPORT trebuie sa fie LOCAL_MAILPIT sau SMTP.")
    return transport


def mail_settings(transport=None):
    transport = transport or configured_transport()
    local = transport == "LOCAL_MAILPIT"
    if transport not in ("LOCAL_MAILPIT", "SMTP"):
        raise ValueError("Transportul email nu este valid.")
    port_key = "MAILPIT_SMTP_PORT" if local else "SMTP_PORT"
    try:
        port = int(current_app.config.get(port_key, "1025" if local else "587"))
        if not 1 <= port <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f"{port_key} trebuie sa fie intre 1 si 65535.") from None
    if local:
        host = current_app.config.get("MAILPIT_SMTP_HOST", "127.0.0.1")
        if host not in ("127.0.0.1", "localhost", "::1", "mailpit"):
            raise ValueError("MAILPIT_SMTP_HOST trebuie sa fie local sau serviciul Docker mailpit.")
        return {"transport": transport, "host": host, "port": port, "security": "LOCAL", "sender": "ruris@example.test",
                "username": "", "password": ""}
    host = current_app.config.get("SMTP_HOST", "")
    security = current_app.config.get("SMTP_SECURITY", "STARTTLS")
    username, password = current_app.config.get("SMTP_USERNAME", ""), current_app.config.get("SMTP_PASSWORD", "")
    if not isinstance(host, str) or not host or any(character.isspace() for character in host) or "/" in host:
        raise ValueError("Completeaza SMTP_HOST cu numele serverului.")
    if security not in ("STARTTLS", "SSL"):
        raise ValueError("SMTP_SECURITY trebuie sa fie STARTTLS sau SSL.")
    if not isinstance(username, str) or not isinstance(password, str) or bool(username) != bool(password):
        raise ValueError("SMTP_USERNAME si SMTP_PASSWORD se completeaza impreuna.")
    try:
        sender = validate_email(current_app.config.get("SMTP_FROM_EMAIL", ""), check_deliverability=False).normalized
    except (EmailNotValidError, TypeError):
        raise ValueError("Completeaza SMTP_FROM_EMAIL cu o adresa valida.") from None
    return {"transport": transport, "host": host, "port": port, "security": security,
            "sender": sender, "username": username, "password": password}


def send_to_local_mailpit(message):
    return send_email(message, transport="LOCAL_MAILPIT")


def send_email(message, *, transport=None):
    try:
        settings = mail_settings(transport)
    except ValueError as error:
        raise LocalEmailDeliveryError(str(error)) from None
    local = settings["transport"] == "LOCAL_MAILPIT"
    try:
        recipient = validate_email(message["to"], check_deliverability=False).normalized
        email = EmailMessage()
        email["From"] = settings["sender"]
        email["To"] = recipient
        email["Subject"] = message["subject"]
        if message.get("message_id"):
            email["Message-ID"] = message["message_id"]
        email.set_content(message["body"])
    except (ValueError, TypeError, KeyError):
        raise LocalEmailDeliveryError("Mesajul contine campuri de email invalide.") from None
    submission_started = False
    try:
        connection = (smtplib.SMTP_SSL(settings["host"], settings["port"], timeout=10, context=ssl.create_default_context())
                      if settings["security"] == "SSL" else smtplib.SMTP(settings["host"], settings["port"], timeout=5 if local else 10))
        with connection as smtp:
            if settings["security"] == "STARTTLS":
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if settings["username"]:
                smtp.login(settings["username"], settings["password"])
            submission_started = True
            refused = smtp.send_message(email, from_addr=settings["sender"], to_addrs=[recipient])
            if refused:
                raise LocalEmailDeliveryError("Serverul email nu a acceptat destinatarul mesajului.")
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        raise LocalEmailDeliveryError("Mailpit a refuzat mesajul." if local else "Serverul SMTP a refuzat mesajul.") from None
    except (OSError, smtplib.SMTPException):
        raise LocalEmailDeliveryError("Mesajul nu a putut fi trimis catre Mailpit. Verifica serviciul Docker si portul SMTP local." if local
                                      else "Trimiterea SMTP a esuat. Verifica serverul, conexiunea TLS si autentificarea.",
                                      delivery_unknown=submission_started) from None
