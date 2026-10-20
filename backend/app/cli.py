import click
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.services.users import create_initial_admin


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
