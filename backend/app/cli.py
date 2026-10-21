import click
import signal
from threading import Event, current_thread, main_thread
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.services.users import create_initial_admin
from app.services.notifications import build_overdue_digests, build_test_overdue_message
from app.services.mail import LocalEmailDeliveryError, send_to_local_mailpit
from app.services.email_delivery import list_email_deliveries, send_overdue_digests_local
from app.services.notification_worker import run_notification_tick, worker_settings
from app.services.notifications import build_blocked_invoice_digests
from app.services.email_delivery import send_blocked_invoice_digests_local
from app.services.email_delivery import send_notification_digests
from app.services.receipt_notifications import build_buyer_receipt_digests, build_warehouse_receipt_digests
from app.services.mail import configured_transport
from app.services.attachments import check_attachment_storage


@click.command("check-attachments", help="Verifica integritatea fisierelor pastrate, fara modificari.")
@with_appcontext
def check_attachments_command():
    try:
        result = check_attachment_storage()
    except (OSError, SQLAlchemyError):
        raise click.ClickException("Verificarea documentelor nu este disponibila.") from None
    click.echo(f"Fisiere inregistrate: {result['referenced']}; lipsa sau corupte: {result['missing_or_corrupted']}; neasociate: {result['unreferenced']}; temporare: {result['staged']}.")
    if any(result[key] for key in ("missing_or_corrupted", "unreferenced", "staged")):
        raise click.ClickException("Sunt necesare verificari ale spatiului de documente. Nu a fost sters niciun fisier.")


@click.command("preview-receipt-emails", help="Previzualizeaza clarificarile pentru Achizitii si Depozit.")
@with_appcontext
def preview_receipt_emails_command():
    try:
        for builder in (build_buyer_receipt_digests, build_warehouse_receipt_digests):
            digest = builder()
            for message in digest["messages"]:
                click.echo(f"Catre: {message['to']}\nSubiect: {message['subject']}\n\n{message['body']}\n")
            click.echo(f"Mesaje: {len(digest['messages'])}; pozitii fara destinatar: {digest['skipped_items']}.")
    except SQLAlchemyError:
        raise click.ClickException("Clarificarile nu sunt disponibile. Verifica PostgreSQL.") from None


@click.command("send-notification-emails", help="Proceseaza notificarile folosind transportul configurat.")
@with_appcontext
def send_notification_emails_command():
    try:
        result = send_notification_digests()
    except (ValueError, LocalEmailDeliveryError) as error:
        raise click.ClickException(str(error)) from None
    except SQLAlchemyError:
        raise click.ClickException("Jurnalul nu a putut fi actualizat. Verifica PostgreSQL.") from None
    click.echo(f"Transport: {configured_transport()}; acceptate: {result['sent']}.")
    click.echo("Stari: " + ", ".join(f"{status}: {count}" for status, count in sorted(result["states"].items())))
    if result["skipped_items"]:
        click.echo(f"Pozitii fara destinatar eligibil: {result['skipped_items']}.")
    if any(result["states"].get(status) for status in ("FAILED", "UNKNOWN", "SENDING")):
        raise click.ClickException("Exista trimiteri nereusite sau neclare. Consulta jurnalul notificarilor.")


@click.command("preview-blocked-invoice-emails", help="Previzualizeaza sumarul facturilor blocate, fara trimitere.")
@with_appcontext
def preview_blocked_invoice_emails_command():
    try:
        digest = build_blocked_invoice_digests()
    except SQLAlchemyError:
        raise click.ClickException("Sumarul facturilor nu este disponibil. Verifica PostgreSQL.") from None
    click.echo(f"Previzualizare pentru {digest['as_of']}. Mesaje: {len(digest['messages'])}.")
    for message in digest["messages"]:
        click.echo(f"\nCatre: {message['to']}\nSubiect: {message['subject']}\n\n{message['body']}")
    if digest["skipped_items"]:
        click.echo(f"Motive fara destinatar activ din contabilitate: {digest['skipped_items']}.")


@click.command("send-blocked-invoice-emails-local", help="Trimite sumarul facturilor blocate numai in Mailpit local.")
@with_appcontext
def send_blocked_invoice_emails_local_command():
    try:
        result = send_blocked_invoice_digests_local()
    except SQLAlchemyError:
        raise click.ClickException("Jurnalul facturilor nu a putut fi actualizat. Verifica PostgreSQL.") from None
    click.echo(f"Mesaje acceptate de Mailpit local: {result['sent']}.")
    click.echo("Stari: " + ", ".join(f"{status}: {count}" for status, count in sorted(result["states"].items())))
    if result["skipped_items"]:
        click.echo(f"Motive fara destinatar activ din contabilitate: {result['skipped_items']}.")
    if result["states"].get("FAILED") or result["states"].get("UNKNOWN"):
        raise click.ClickException("Exista trimiteri nereusite sau neclare; consulta jurnalul.")


@click.command("create-admin", help="Creeaza primul administrator si inregistreaza auditul.")
@click.option("--name", prompt="Nume")
@click.option("--email", prompt="Email")
@with_appcontext
def create_admin_command(name, email):
    """Create the first administrator and its audit event."""
    password = click.prompt("Parola", hide_input=True, confirmation_prompt="Repeta parola")
    try:
        create_initial_admin(name=name, email=email, password=password)
    except ValueError as error:
        raise click.ClickException(str(error)) from None
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_users_email":
            raise click.ClickException("Emailul este deja folosit de un cont.") from None
        raise click.ClickException("Contul nu a fost creat. Verifica integritatea bazei de date.") from None
    except SQLAlchemyError:
        raise click.ClickException("Contul nu a fost creat. Verifica PostgreSQL si migrarile.") from None
    click.echo("Administratorul initial a fost creat, impreuna cu auditul.")


@click.command("preview-overdue-emails", help="Previzualizeaza sumarul intarzierilor pentru responsabilii din achizitii.")
@with_appcontext
def preview_overdue_emails_command():
    """Preview overdue emails without sending them."""
    try:
        digest = build_overdue_digests()
    except SQLAlchemyError:
        raise click.ClickException("Sumarul nu a putut fi generat. Verifica PostgreSQL si migrarile.") from None
    click.echo(f"Previzualizare pentru {digest['as_of']} ({digest['timezone']}). Nu sunt trimise emailuri.")
    click.echo(f"Mesaje pregatite: {len(digest['messages'])}.")
    for message in digest["messages"]:
        click.echo(f"\nCatre: {message['to']}\nSubiect: {message['subject']}\n\n{message['body']}")
    if digest["skipped_items"]:
        click.echo(f"\nPozitii fara responsabil activ cu rolul ACHIZITII: {digest['skipped_items']}.")


@click.command("send-test-email", help="Trimite un sumar demonstrativ numai catre Mailpit local.")
@with_appcontext
def send_test_email_command():
    """Send a synthetic digest to local Mailpit."""
    try:
        send_to_local_mailpit(build_test_overdue_message())
    except LocalEmailDeliveryError as error:
        raise click.ClickException(str(error)) from None
    except SQLAlchemyError:
        raise click.ClickException("Mesajul de test nu a putut fi pregatit. Verifica PostgreSQL.") from None
    click.echo("Sumarul demonstrativ a fost acceptat de Mailpit local. Deschide inboxul de test in browser.")


@click.command("send-overdue-emails-local", help="Trimite sumarele intarzierilor numai catre Mailpit local.")
@with_appcontext
def send_overdue_emails_local_command():
    """Send overdue digests to local Mailpit."""
    try:
        result = send_overdue_digests_local()
    except SQLAlchemyError:
        raise click.ClickException("Jurnalul nu a putut fi actualizat. Verifica PostgreSQL; mesajele SENDING necesita verificare in Mailpit.") from None
    click.echo(f"Mesaje acceptate de Mailpit local: {result['sent']}.")
    click.echo("Stari pentru ziua curenta: " + ", ".join(f"{status}: {count}" for status, count in sorted(result["states"].items())))
    if result["skipped_items"]:
        click.echo(f"Pozitii fara responsabil activ cu rolul ACHIZITII: {result['skipped_items']}.")
    if result["states"].get("FAILED") or result["states"].get("UNKNOWN"):
        raise click.ClickException(f"Exista trimiteri nereusite sau neclare. Mesaje acceptate anterior in aceasta rulare: {result['sent']}.")


@click.command("list-email-deliveries", help="Afiseaza jurnalul sumarurilor email locale.")
@click.option("--limit", type=click.IntRange(1, 100), default=20, show_default=True)
@with_appcontext
def list_email_deliveries_command(limit):
    """List local email delivery states."""
    try:
        deliveries = list_email_deliveries(limit=limit)
    except SQLAlchemyError:
        raise click.ClickException("Jurnalul nu este disponibil. Verifica PostgreSQL si migrarile.") from None
    if not deliveries:
        click.echo("Nu exista mesaje in jurnal.")
    for delivery in deliveries:
        click.echo(f"ID {delivery['id']} | {delivery['kind']} | {delivery['as_of']} | utilizator {delivery['recipient_user_id']} | "
                   f"{delivery['status']} | incercari {delivery['attempt_count']} | {delivery['last_error'] or '-'}")
        if delivery["next_attempt_at"]:
            click.echo(f"  Urmatoarea incercare (UTC): {delivery['next_attempt_at'].isoformat()}")


@click.command("run-notification-worker", help="Ruleaza programarea zilnica a notificarilor email.")
@click.option("--once", is_flag=True, help="Verifica o singura data ora si mesajele eligibile.")
@click.option("--poll-seconds", type=click.IntRange(1, 60), default=60, show_default=True)
@with_appcontext
def run_notification_worker_command(once, poll_seconds):
    """Run the notification worker."""
    try:
        daily_time, retry_seconds = worker_settings()
    except ValueError as error:
        raise click.ClickException(str(error)) from None
    click.echo(f"Notificari {configured_transport()} la {daily_time:%H:%M} Europe/Bucharest; reincercare dupa {retry_seconds} secunde.")
    stop = Event()
    completed_date = None
    previous_handler = None
    if not once and current_thread() is main_thread():
        previous_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda signum, frame: stop.set())
    try:
        while True:
            try:
                result = run_notification_tick(last_completed_date=completed_date)
                completed_date = result["last_completed_date"]
                if result["ran"]:
                    states = ", ".join(f"{status}: {count}" for status, count in sorted(result["states"].items()))
                    click.echo(f"{result['local_time']} | acceptate: {result['sent']} | {states or 'fara mesaje'}")
                    if result["skipped_items"]:
                        click.echo(f"Pozitii fara responsabil eligibil: {result['skipped_items']}.")
                elif once:
                    click.echo(f"{result['local_time']} | Nu este necesara procesarea acum.")
            except SQLAlchemyError:
                click.echo("Verificarea a esuat. PostgreSQL indisponibil sau jurnal neactualizat; SENDING necesita verificare.", err=True)
                if once:
                    raise click.ClickException("Verificarea nu a putut fi finalizata.") from None
            if once or stop.wait(poll_seconds):
                break
    except KeyboardInterrupt:
        click.echo("Workerul a fost oprit.")
    finally:
        if previous_handler is not None:
            signal.signal(signal.SIGTERM, previous_handler)
