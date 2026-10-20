from unittest.mock import Mock

import pytest

from app.models import Role, User
from app.services import audit


@pytest.fixture
def session(monkeypatch):
    session = Mock(spec=["add"])
    monkeypatch.setattr(audit.db, "session", session)
    return session


def record(**changes):
    values = {
        "action": "UPDATE", "entity_type": "users", "entity_id": 7,
        "actor_user_id": 1, "before": {"is_active": True},
        "after": {"is_active": False},
    }
    values.update(changes)
    return audit.record_audit(**values)


def test_audit_is_added_without_committing_the_callers_transaction(session):
    event = record(reason=" Cont dezactivat ")
    session.add.assert_called_once_with(event)
    assert event.actor_user_id == 1
    assert event.entity_id == 7
    assert event.before_data == {"is_active": True}
    assert event.after_data == {"is_active": False}
    assert event.reason == "Cont dezactivat"


def test_automatic_operation_identifies_its_process(session):
    event = record(actor_user_id=None, actor_process=" initial_setup ", action="CREATE")
    assert event.actor_user_id is None
    assert event.actor_process == "initial_setup"


@pytest.mark.parametrize("authors", [
    {"actor_user_id": None},
    {"actor_process": "worker"},
    {"actor_user_id": 0},
    {"actor_user_id": True},
    {"actor_user_id": None, "actor_process": " "},
])
def test_missing_or_ambiguous_author_is_rejected(session, authors):
    with pytest.raises(ValueError):
        record(**authors)
    session.add.assert_not_called()


@pytest.mark.parametrize("field", ["password", "password_hash", "access_token", "refresh_token"])
def test_secrets_cannot_be_included_in_a_snapshot(session, field):
    with pytest.raises(ValueError):
        record(after={field: "secret-de-test"})
    session.add.assert_not_called()


def test_nested_data_cannot_hide_secrets_in_allowed_fields(session):
    with pytest.raises(ValueError):
        record(after={"name": {"password": "secret-de-test"}})
    session.add.assert_not_called()


def test_snapshot_is_independent_of_the_input_dictionary(session):
    after = {"name": "Ana"}
    event = record(after=after)
    after["name"] = "Alt nume"
    assert event.after_data == {"name": "Ana"}


def test_password_change_records_action_without_password_values(session):
    event = record(action="PASSWORD_CHANGE", before=None, after=None)
    assert event.action == "PASSWORD_CHANGE"
    assert event.before_data is None
    assert event.after_data is None


def test_user_snapshot_selects_only_permitted_fields():
    user = User(
        name="Ana", email="ana@example.com", role=Role.DEPOZIT,
        is_active=True, password_hash="hash-care-nu-trebuie-copiat", token_version=3,
    )
    assert audit.user_snapshot(user) == {
        "name": "Ana", "email": "ana@example.com",
        "role": "DEPOZIT", "is_active": True,
    }


@pytest.mark.parametrize("changes", [
    {"entity_id": -1}, {"entity_id": True}, {"entity_type": "invoices"},
    {"action": "UNKNOWN"}, {"after": {"role": "MANAGER"}},
])
def test_unconfigured_operations_and_invalid_values_are_rejected(session, changes):
    with pytest.raises(ValueError):
        record(**changes)
    session.add.assert_not_called()
