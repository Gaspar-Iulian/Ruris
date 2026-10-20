from uuid import uuid4

import pytest
from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import AuditEvent, Role, User
from app.services import users


def credentials():
    return {
        "name": "Administrator test", "email": f"admin-{uuid4().hex}@example.com",
        "password": "parola-numai-pentru-test-admin",
    }


def test_command_creates_admin_with_audit_and_hides_password(session):
    values = credentials()
    result = current_app.test_cli_runner().invoke(
        args=["create-admin"],
        input=f"{values['name']}\n{values['email']}\n{values['password']}\n{values['password']}\n",
    )
    assert result.exit_code == 0, result.output
    assert values["password"] not in result.output
    assert "impreuna cu auditul" in result.output
    user = session.scalar(select(User).where(User.email == values["email"]))
    assert user.role == Role.ADMIN
    assert user.is_active
    assert user.check_password(values["password"])
    audit = session.scalar(select(AuditEvent).where(AuditEvent.entity_id == user.id))
    assert audit.action == "CREATE"
    assert audit.actor_process == "initial_setup"
    assert audit.actor_user_id is None
    assert "password_hash" not in audit.after_data


@pytest.mark.parametrize("active", [True, False])
def test_existing_admin_even_inactive_blocks_initialization(session, active):
    user = users.create_initial_admin(**credentials())
    user.is_active = active
    session.commit()
    with pytest.raises(users.InitialAdminExistsError):
        users.create_initial_admin(**credentials())
    assert session.scalar(select(func.count()).select_from(User)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_invalid_password_does_not_create_user_or_audit(session):
    values = credentials()
    values["password"] = "scurta"
    result = current_app.test_cli_runner().invoke(
        args=["create-admin", "--name", values["name"], "--email", values["email"]],
        input=f"{values['password']}\n{values['password']}\n",
    )
    assert result.exit_code != 0
    assert "cel putin 12" in result.output
    assert values["password"] not in result.output
    assert session.scalar(select(func.count()).select_from(User)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_password_confirmation_must_match(session):
    values = credentials()
    result = current_app.test_cli_runner().invoke(
        args=["create-admin", "--name", values["name"], "--email", values["email"]],
        input=f"{values['password']}\nparola-diferita\n",
    )
    assert result.exit_code != 0
    assert values["password"] not in result.output
    assert session.scalar(select(func.count()).select_from(User)) == 0


def test_audit_failure_rolls_back_admin_creation(session, monkeypatch):
    def fail_audit(**kwargs):
        raise RuntimeError("Audit indisponibil")

    monkeypatch.setattr(users, "record_audit", fail_audit)
    with pytest.raises(RuntimeError, match="Audit indisponibil"):
        users.create_initial_admin(**credentials())
    assert session.scalar(select(func.count()).select_from(User)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_existing_non_admin_email_is_not_promoted(session):
    values = credentials()
    user = User(name=values["name"], email=values["email"], role=Role.DEPOZIT)
    user.set_password(values["password"])
    session.add(user)
    session.commit()
    with pytest.raises(IntegrityError):
        users.create_initial_admin(**values)
    assert session.scalar(select(User.role).where(User.email == values["email"])) == Role.DEPOZIT
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
