import click
from threading import Event
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.services.users import create_initial_admin
from app.services.notifications import build_overdue_digests, build_test_overdue_message
from app.services.mail import LocalEmailDeliveryError, send_to_local_mailpit
from app.services.email_delivery import list_email_deliveries, send_overdue_digests_local
from app.services.notification_worker import run_notification_tick, worker_settings


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
        click.echo(f"ID {delivery['id']} | {delivery['as_of']} | utilizator {delivery['recipient_user_id']} | "
                   f"{delivery['status']} | incercari {delivery['attempt_count']} | {delivery['last_error'] or '-'}")
        if delivery["next_attempt_at"]:
            click.echo(f"  Urmatoarea incercare (UTC): {delivery['next_attempt_at'].isoformat()}")


@click.command("run-notification-worker", help="Ruleaza programarea zilnica a emailurilor catre Mailpit local.")
@click.option("--once", is_flag=True, help="Verifica o singura data ora si mesajele eligibile.")
@click.option("--poll-seconds", type=click.IntRange(1, 60), default=60, show_default=True)
@with_appcontext
def run_notification_worker_command(once, poll_seconds):
    """Run the local notification worker."""
    try:
        daily_time, retry_seconds = worker_settings()
    except ValueError as error:
        raise click.ClickException(str(error)) from None
    click.echo(f"Notificari locale la {daily_time:%H:%M} Europe/Bucharest; reincercare dupa {retry_seconds} secunde.")
    stop = Event()
    completed_date = None
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
