from uuid import uuid4

from flask import current_app
from flask_jwt_extended import create_access_token, get_csrf_token
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import AuditEvent, Role, User
from app.services import users


@pytest.fixture
def accounts(session):
    result = {}
    for key, role in (("admin", Role.ADMIN), ("target", Role.DEPOZIT)):
        password = "parola-pentru-test-stare"
        user = User(name="Cont test", email=f"status-{uuid4().hex}@example.com", role=role, is_active=True)
        user.set_password(password)
        session.add(user)
        session.flush()
        result[key] = {"id": user.id, "email": user.email, "password": password, "token_version": user.token_version}
    session.commit()
    return result


@pytest.fixture
def client(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    return current_app.test_client()


def authorize(client, account):
    token = create_access_token(identity=str(account["id"]), additional_claims={"token_version": account["token_version"]})
    client.set_cookie("access_token_cookie", token, path="/api")
    return {"X-CSRF-TOKEN": get_csrf_token(token)}


def change_status(client, user_id, headers, active=False):
    return client.patch(
        f"/api/users/{user_id}/status", headers=headers,
        json={"is_active": active, "reason": " Schimbare aprobata "},
    )


def test_deactivation_invalidates_sessions_and_records_actor_reason_and_values(client, session, accounts):
    headers = authorize(client, accounts["admin"])
    target_client = current_app.test_client()
    authorize(target_client, accounts["target"])
    assert target_client.get("/api/auth/me").status_code == 200
    response = change_status(client, accounts["target"]["id"], headers)
    assert response.status_code == 200
    assert response.get_json()["user"]["is_active"] is False
    assert "Set-Cookie" not in response.headers
    assert target_client.get("/api/auth/me").status_code == 401
    stored = session.get(User, accounts["target"]["id"])
    assert stored.token_version == accounts["target"]["token_version"] + 1
    event = session.scalar(select(AuditEvent))
    assert event.action == "DEACTIVATE"
    assert event.actor_user_id == accounts["admin"]["id"]
    assert event.entity_id == accounts["target"]["id"]
    assert event.before_data["is_active"] is True
    assert event.after_data["is_active"] is False
    assert event.reason == "Schimbare aprobata"


def test_reactivation_requires_new_login_and_does_not_restore_old_token(client, session, accounts):
    headers = authorize(client, accounts["admin"])
    old_client = current_app.test_client()
    authorize(old_client, accounts["target"])
    target_id = accounts["target"]["id"]
    assert change_status(client, target_id, headers).status_code == 200
    assert change_status(client, target_id, headers, active=True).status_code == 200
    fresh_client = current_app.test_client()
    login = fresh_client.post("/api/auth/login", json={
        "email": accounts["target"]["email"], "password": accounts["target"]["password"],
    })
    assert login.status_code == 200
    assert old_client.get("/api/auth/me").status_code == 401
    assert fresh_client.get("/api/auth/me").status_code == 200
    assert session.get(User, target_id).token_version == accounts["target"]["token_version"] + 2
    events = session.scalars(select(AuditEvent.action).where(AuditEvent.action.in_(["ACTIVATE", "DEACTIVATE"])).order_by(AuditEvent.id)).all()
    assert events == ["DEACTIVATE", "ACTIVATE"]


def test_unchanged_status_does_not_invalidate_session_or_duplicate_audit(client, session, accounts):
    headers = authorize(client, accounts["admin"])
    for _ in range(2):
        assert change_status(client, accounts["target"]["id"], headers, active=True).status_code == 200
    assert session.get(User, accounts["target"]["id"]).token_version == accounts["target"]["token_version"]
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_last_active_administrator_cannot_be_deactivated(client, session, accounts):
    headers = authorize(client, accounts["admin"])
    response = change_status(client, accounts["admin"]["id"], headers)
    assert response.status_code == 409
    assert client.get("/api/auth/me").status_code == 200
    assert session.get(User, accounts["admin"]["id"]).is_active is True
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_two_administrators_cannot_both_be_deactivated(client, session, accounts):
    session.get(User, accounts["target"]["id"]).role = Role.ADMIN
    session.commit()
    headers = authorize(client, accounts["admin"])
    assert change_status(client, accounts["target"]["id"], headers).status_code == 200
    assert change_status(client, accounts["admin"]["id"], headers).status_code == 409
    assert session.scalar(select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.is_active.is_(True))) == 1


def test_audit_failure_rolls_back_status_and_token_version(client, session, accounts, monkeypatch):
    headers = authorize(client, accounts["admin"])

    def unavailable(**kwargs):
        raise SQLAlchemyError("detalii interne")

    monkeypatch.setattr(users, "record_audit", unavailable)
    response = change_status(client, accounts["target"]["id"], headers)
    assert response.status_code == 503
    assert "detalii interne" not in response.get_data(as_text=True)
    target = session.get(User, accounts["target"]["id"])
    assert target.is_active is True
    assert target.token_version == accounts["target"]["token_version"]
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("role", [Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE])
def test_team_roles_cannot_change_account_status(client, session, accounts, role):
    session.get(User, accounts["admin"]["id"]).role = role
    session.commit()
    headers = authorize(client, accounts["admin"])
    assert change_status(client, accounts["target"]["id"], headers).status_code == 403
    assert session.get(User, accounts["target"]["id"]).is_active is True


@pytest.mark.parametrize("headers", [{}, {"X-CSRF-TOKEN": "gresit"}])
def test_status_change_requires_csrf(client, session, accounts, headers):
    authorize(client, accounts["admin"])
    assert change_status(client, accounts["target"]["id"], headers).status_code == 401


def test_status_change_requires_authentication(client, accounts):
    assert change_status(client, accounts["target"]["id"], {}).status_code == 401


@pytest.mark.parametrize("body", [
    {}, {"is_active": False}, {"is_active": "false", "reason": "Test"},
    {"is_active": 0, "reason": "Test"}, {"is_active": None, "reason": "Test"},
    {"is_active": False, "reason": " "}, {"is_active": False, "reason": None},
    {"is_active": False, "reason": "a" * 1001},
    {"is_active": False, "reason": "Test", "role": "ADMIN"},
])
def test_invalid_status_payload_is_rejected(client, session, accounts, body):
    headers = authorize(client, accounts["admin"])
    response = client.patch(f"/api/users/{accounts['target']['id']}/status", headers=headers, json=body)
    assert response.status_code == 400
    assert session.get(User, accounts["target"]["id"]).is_active is True
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("user_id", [0, 9223372036854775807, 9223372036854775808])
def test_unknown_or_out_of_range_account_returns_404(client, accounts, user_id):
    headers = authorize(client, accounts["admin"])
    assert change_status(client, user_id, headers).status_code == 404


@pytest.mark.parametrize("data,content_type,status", [
    ("{", "application/json", 400), ("a" * 5000, "application/json", 413),
    ("is_active=false", "application/x-www-form-urlencoded", 415),
])
def test_status_request_format_and_size_are_checked(client, accounts, data, content_type, status):
    headers = authorize(client, accounts["admin"])
    response = client.patch(f"/api/users/{accounts['target']['id']}/status", headers=headers, data=data, content_type=content_type)
    assert response.status_code == status


def test_service_rechecks_administrator_role(session, accounts):
    with pytest.raises(users.UserManagementForbiddenError):
        users.set_user_active(
            actor_user_id=accounts["target"]["id"], user_id=accounts["admin"]["id"],
            is_active=False, reason="Test",
        )
    assert session.get(User, accounts["admin"]["id"]).is_active is True


def test_administrator_changes_hold_a_cross_connection_transaction_lock(client, accounts):
    headers = authorize(client, accounts["admin"])
    assert change_status(client, accounts["target"]["id"], headers).status_code == 200
    with db.engine.connect() as other_connection:
        acquired = other_connection.scalar(select(func.pg_try_advisory_xact_lock(users.ADMIN_WRITE_LOCK_ID)))
        assert acquired is False
