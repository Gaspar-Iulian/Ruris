from uuid import uuid4

from flask import current_app
from flask_jwt_extended import create_access_token, get_csrf_token
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models import AuditEvent, Role, User
from app.services import users


@pytest.fixture
def accounts(session):
    values = {}
    for key, role in (("admin", Role.ADMIN), ("target", Role.DEPOZIT)):
        password = "parola-pentru-test-schimbare-rol"
        user = User(name="Cont test", email=f"role-change-{uuid4().hex}@example.com", role=role, is_active=True)
        user.set_password(password)
        session.add(user)
        session.flush()
        values[key] = {"id": user.id, "email": user.email, "password": password, "token_version": user.token_version}
    session.commit()
    return values


@pytest.fixture
def client(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    return current_app.test_client()


def authorize(client, account):
    token = create_access_token(identity=str(account["id"]), additional_claims={"token_version": account["token_version"]})
    client.set_cookie("access_token_cookie", token, path="/api")
    return {"X-CSRF-TOKEN": get_csrf_token(token)}


def change_role(client, user_id, headers, role="ACHIZITII"):
    return client.patch(
        f"/api/users/{user_id}/role", headers=headers,
        json={"role": role, "reason": " Mutare aprobata "},
    )


@pytest.mark.parametrize("old_role,new_role", [
    (Role.DEPOZIT, Role.ACHIZITII), (Role.DEPOZIT, Role.CONTABILITATE),
    (Role.DEPOZIT, Role.ADMIN), (Role.ACHIZITII, Role.DEPOZIT),
])
def test_role_change_is_audited_and_requires_fresh_login(client, session, accounts, old_role, new_role):
    session.get(User, accounts["target"]["id"]).role = old_role
    session.commit()
    headers = authorize(client, accounts["admin"])
    old_client = current_app.test_client()
    authorize(old_client, accounts["target"])
    response = change_role(client, accounts["target"]["id"], headers, new_role.value)
    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == new_role.value
    assert "Set-Cookie" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
    fresh_client = current_app.test_client()
    assert fresh_client.post("/api/auth/login", json={
        "email": accounts["target"]["email"], "password": accounts["target"]["password"],
    }).status_code == 200
    assert old_client.get("/api/auth/me").status_code == 401
    assert fresh_client.get("/api/auth/me").get_json()["user"]["role"] == new_role.value
    assert fresh_client.get("/api/users").status_code == (200 if new_role == Role.ADMIN else 403)
    target = session.get(User, accounts["target"]["id"])
    assert target.token_version == accounts["target"]["token_version"] + 1
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "ROLE_CHANGE"))
    assert event.actor_user_id == accounts["admin"]["id"]
    assert event.entity_id == target.id
    assert event.before_data["role"] == old_role.value
    assert event.after_data["role"] == new_role.value
    assert event.reason == "Mutare aprobata"


def test_same_role_does_not_change_sessions_or_duplicate_audit(client, session, accounts):
    headers = authorize(client, accounts["admin"])
    for _ in range(2):
        assert change_role(client, accounts["target"]["id"], headers, "DEPOZIT").status_code == 200
    assert session.get(User, accounts["target"]["id"]).token_version == accounts["target"]["token_version"]
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_last_administrator_cannot_lose_admin_role(client, session, accounts):
    headers = authorize(client, accounts["admin"])
    assert change_role(client, accounts["admin"]["id"], headers).status_code == 409
    assert client.get("/api/auth/me").status_code == 200
    assert session.get(User, accounts["admin"]["id"]).role == Role.ADMIN
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_administration_can_be_handed_over_to_another_active_account(client, session, accounts):
    headers = authorize(client, accounts["admin"])
    assert change_role(client, accounts["target"]["id"], headers, "ADMIN").status_code == 200
    assert change_role(client, accounts["admin"]["id"], headers, "DEPOZIT").status_code == 200
    new_admin = current_app.test_client()
    assert new_admin.post("/api/auth/login", json={
        "email": accounts["target"]["email"], "password": accounts["target"]["password"],
    }).status_code == 200
    assert new_admin.get("/api/users").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert session.scalar(select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.is_active.is_(True))) == 1


def test_promoting_inactive_account_does_not_remove_last_admin_protection(client, session, accounts):
    session.get(User, accounts["target"]["id"]).is_active = False
    session.commit()
    headers = authorize(client, accounts["admin"])
    response = change_role(client, accounts["target"]["id"], headers, "ADMIN")
    assert response.status_code == 200
    assert response.get_json()["user"]["is_active"] is False
    assert change_role(client, accounts["admin"]["id"], headers, "DEPOZIT").status_code == 409


def test_status_and_role_changes_share_last_admin_protection(client, accounts):
    headers = authorize(client, accounts["admin"])
    assert change_role(client, accounts["target"]["id"], headers, "ADMIN").status_code == 200
    response = client.patch(
        f"/api/users/{accounts['target']['id']}/status", headers=headers,
        json={"is_active": False, "reason": "Test"},
    )
    assert response.status_code == 200
    assert change_role(client, accounts["admin"]["id"], headers).status_code == 409


def test_audit_failure_rolls_back_role_and_session_version(client, session, accounts, monkeypatch):
    headers = authorize(client, accounts["admin"])

    def unavailable(**kwargs):
        raise SQLAlchemyError("detalii interne")

    monkeypatch.setattr(users, "record_audit", unavailable)
    response = change_role(client, accounts["target"]["id"], headers)
    assert response.status_code == 503
    assert "detalii interne" not in response.get_data(as_text=True)
    target = session.get(User, accounts["target"]["id"])
    assert target.role == Role.DEPOZIT
    assert target.token_version == accounts["target"]["token_version"]
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("role", [Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE])
def test_team_roles_cannot_assign_roles(client, session, accounts, role):
    session.get(User, accounts["admin"]["id"]).role = role
    session.commit()
    headers = authorize(client, accounts["admin"])
    assert change_role(client, accounts["target"]["id"], headers, "ADMIN").status_code == 403


@pytest.mark.parametrize("headers", [{}, {"X-CSRF-TOKEN": "gresit"}])
def test_role_change_requires_csrf(client, accounts, headers):
    authorize(client, accounts["admin"])
    assert change_role(client, accounts["target"]["id"], headers).status_code == 401


def test_role_change_requires_authentication(client, accounts):
    assert change_role(client, accounts["target"]["id"], {}).status_code == 401


@pytest.mark.parametrize("body", [
    {}, {"role": "DEPOZIT"}, {"role": "MANAGER", "reason": "Test"},
    {"role": "WAREHOUSE", "reason": "Test"}, {"role": None, "reason": "Test"},
    {"role": ["ADMIN"], "reason": "Test"}, {"role": "ADMIN", "reason": " "},
    {"role": "ADMIN", "reason": "a" * 1001}, {"role": "ADMIN", "reason": None},
    {"role": "ADMIN", "reason": "Test", "is_active": True},
])
def test_invalid_role_payload_is_rejected(client, session, accounts, body):
    headers = authorize(client, accounts["admin"])
    response = client.patch(f"/api/users/{accounts['target']['id']}/role", headers=headers, json=body)
    assert response.status_code == 400
    assert session.get(User, accounts["target"]["id"]).role == Role.DEPOZIT
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("user_id", [0, 9223372036854775807, 9223372036854775808])
def test_role_change_for_unknown_account_returns_404(client, accounts, user_id):
    headers = authorize(client, accounts["admin"])
    assert change_role(client, user_id, headers).status_code == 404


@pytest.mark.parametrize("data,content_type,status", [
    ("{", "application/json", 400), ("a" * 5000, "application/json", 413),
    ("role=ADMIN", "application/x-www-form-urlencoded", 415),
])
def test_role_request_format_and_size_are_validated(client, accounts, data, content_type, status):
    headers = authorize(client, accounts["admin"])
    response = client.patch(f"/api/users/{accounts['target']['id']}/role", headers=headers, data=data, content_type=content_type)
    assert response.status_code == status


def test_role_service_rechecks_actor_permissions(session, accounts):
    with pytest.raises(users.UserManagementForbiddenError):
        users.set_user_role(
            actor_user_id=accounts["target"]["id"], user_id=accounts["target"]["id"],
            role="ADMIN", reason="Test",
        )
