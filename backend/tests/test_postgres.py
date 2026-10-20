from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from app.models import AuditEvent, Role, User
from app.services.audit import record_audit, user_snapshot


def create_user(session, **changes):
    values = {
        "name": "Utilizator test", "email": f"test-{uuid4().hex}@example.com",
        "role": Role.ACHIZITII,
    }
    values.update(changes)
    user = User(**values)
    user.set_password("parola-numai-pentru-teste")
    session.add(user)
    session.flush()
    return user


def audit_user(user):
    return record_audit(
        action="CREATE", entity_type="users", entity_id=user.id,
        actor_user_id=user.id, after=user_snapshot(user),
    )


def test_user_and_audit_can_be_loaded_from_postgres(session):
    user = create_user(session)
    audit = audit_user(user)
    session.flush()
    user_id, audit_id = user.id, audit.id
    session.expunge_all()
    stored_user = session.get(User, user_id)
    stored_audit = session.get(AuditEvent, audit_id)
    assert stored_user.is_active is True
    assert stored_user.role == Role.ACHIZITII
    assert stored_user.check_password("parola-numai-pentru-teste")
    assert stored_audit.after_data == user_snapshot(stored_user)
    assert stored_audit.actor_user_id == stored_user.id
    assert stored_audit.created_at.utcoffset() is not None


def test_normalized_duplicate_email_is_rejected_by_postgres(session):
    first = create_user(session)
    with pytest.raises(IntegrityError) as error:
        create_user(session, email=f" {first.email.upper()} ")
    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == "uq_users_email"


@pytest.mark.parametrize("statement", [
    "UPDATE users SET role = 'MANAGER' WHERE id = :id",
    "UPDATE users SET name = ' ' WHERE id = :id",
    "UPDATE users SET token_version = -1 WHERE id = :id",
    "UPDATE users SET email = upper(email) WHERE id = :id",
])
def test_user_constraints_also_protect_direct_sql(session, statement):
    user = create_user(session)
    with pytest.raises(IntegrityError) as error:
        session.execute(text(statement), {"id": user.id})
    assert error.value.orig.sqlstate == "23514"


@pytest.mark.parametrize("statement", [
    "UPDATE audit_events SET reason = 'rescris' WHERE id = :id",
    "DELETE FROM audit_events WHERE id = :id",
])
def test_postgres_trigger_prevents_audit_changes(session, statement):
    user = create_user(session)
    audit = audit_user(user)
    session.flush()
    with pytest.raises(DBAPIError) as error:
        session.execute(text(statement), {"id": audit.id})
    assert error.value.orig.sqlstate == "P0001"
    assert "audit" in str(error.value.orig).lower()


def test_orm_also_rejects_editing_an_audit_event(session):
    audit = audit_user(create_user(session))
    session.flush()
    audit.reason = "Rescriere"
    with pytest.raises(ValueError, match="nu pot fi modificate"):
        session.flush()


def test_user_with_audit_history_cannot_be_deleted(session):
    user = create_user(session)
    audit_user(user)
    session.flush()
    with pytest.raises(IntegrityError) as error:
        session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    assert error.value.orig.sqlstate == "23503"


def test_error_after_audit_rolls_back_both_user_change_and_audit(session):
    user = create_user(session)
    user_id = user.id
    original_name = user.name
    session.commit()
    with pytest.raises(RuntimeError, match="Eroare simulata"):
        with session.begin():
            user = session.get(User, user_id)
            before = user_snapshot(user)
            user.name = "Nume schimbat"
            record_audit(
                action="UPDATE", entity_type="users", entity_id=user_id,
                actor_user_id=user_id, before=before, after=user_snapshot(user),
            )
            session.flush()
            raise RuntimeError("Eroare simulata")
    assert session.get(User, user_id).name == original_name
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.entity_type == "users", AuditEvent.entity_id == user_id,
    )) == 0


def test_invalid_audit_rolls_back_the_business_change(session):
    user = create_user(session)
    user_id = user.id
    original_name = user.name
    session.commit()
    with pytest.raises(IntegrityError) as error:
        with session.begin():
            user = session.get(User, user_id)
            before = user_snapshot(user)
            user.name = "Schimbare fara audit valid"
            record_audit(
                action="UPDATE", entity_type="users", entity_id=user_id,
                actor_user_id=9223372036854775807,
                before=before, after=user_snapshot(user),
            )
            session.flush()
    assert error.value.orig.sqlstate == "23503"
    assert session.get(User, user_id).name == original_name
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.entity_type == "users", AuditEvent.entity_id == user_id,
    )) == 0


@pytest.mark.parametrize("actors", [
    {"actor_user_id": None, "actor_process": None},
    {"actor_process": "worker"},
])
def test_postgres_requires_exactly_one_audit_author(session, actors):
    user = create_user(session)
    values = {
        "actor_user_id": user.id, "action": "CREATE",
        "entity_type": "users", "entity_id": user.id,
    }
    values.update(actors)
    session.add(AuditEvent(**values))
    with pytest.raises(IntegrityError) as error:
        session.flush()
    assert error.value.orig.sqlstate == "23514"
