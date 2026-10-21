import os

from flask import current_app


def configure_test_mailpit(app):
    try:
        smtp_port = int(os.getenv("MAILPIT_TEST_SMTP_PORT", "1026"))
        ui_port = int(os.getenv("MAILPIT_TEST_UI_PORT", "8026"))
        app_smtp_port = int(app.config.get("MAILPIT_SMTP_PORT", "1025"))
        app_ui_port = int(os.getenv("MAILPIT_UI_PORT", "8025"))
    except (TypeError, ValueError):
        raise RuntimeError("Porturile Mailpit pentru teste trebuie sa fie numere intregi.") from None
    if (any(not 1 <= port <= 65535 for port in (smtp_port, ui_port))
            or smtp_port == ui_port or {smtp_port, ui_port} & {app_smtp_port, app_ui_port}):
        raise RuntimeError("Mailpit pentru teste trebuie sa aiba porturi valide, separate de cele ale aplicatiei.")
    app.config.update(MAIL_TRANSPORT="LOCAL_MAILPIT", MAILPIT_SMTP_HOST="127.0.0.1", MAILPIT_SMTP_PORT=str(smtp_port),
                      MAILPIT_TEST_UI_PORT=ui_port, MAIL_SUBJECT_PREFIX="[TEST] ")


def mailpit_test_ui_port():
    return current_app.config["MAILPIT_TEST_UI_PORT"]
