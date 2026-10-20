from uuid import uuid4

from flask import current_app
from flask_jwt_extended import create_access_token, get_csrf_token
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models import AuditEvent, Role, User
from app.services import users


@pytest.fixture
def client(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    return current_app.test_client()


def create_actor(session, *, role=Role.ADMIN, active=True):
    actor = User(name="Autor test", email=f"actor-{uuid4().hex}@example.com", role=role, is_active=active)
    actor.set_password("parola-pentru-actor-test")
    session.add(actor)
    session.flush()
    values = {"id": actor.id, "email": actor.email, "token_version": actor.token_version}
    session.commit()
    return values


def authorize(client, account):
    token = create_access_token(identity=str(account["id"]), additional_claims={"token_version": account["token_version"]})
    client.set_cookie("access_token_cookie", token, path="/api")
    return {"X-CSRF-TOKEN": get_csrf_token(token)}


def payload(**changes):
    values = {
        "name": "Ana Test", "email": f"team-{uuid4().hex}@example.com",
        "password": "parola-pentru-contul-test", "role": "ACHIZITII",
    }
    values.update(changes)
    return values


@pytest.mark.parametrize("role", ["ACHIZITII", "DEPOZIT", "CONTABILITATE"])
def test_admin_creates_team_account_with_audit_without_replacing_session(client, session, role):
    admin = create_actor(session)
    headers = authorize(client, admin)
    body = payload(role=role)
    response = client.post("/api/users", json=body, headers=headers)
    assert response.status_code == 201
    assert "Set-Cookie" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
    user_data = response.get_json()["user"]
    assert user_data == {
        "id": user_data["id"], "name": body["name"], "email": body["email"],
        "role": role, "is_active": True,
    }
    assert "password" not in response.get_data(as_text=True)
    teammate = current_app.test_client()
    assert teammate.post("/api/auth/login", json={"email": body["email"], "password": body["password"]}).status_code == 200
    assert client.get("/api/auth/me").get_json()["user"]["id"] == admin["id"]
    assert teammate.get("/api/auth/me").get_json()["user"]["role"] == role
    stored_user = session.get(User, user_data["id"])
    assert stored_user.password_hash != body["password"]
    assert stored_user.check_password(body["password"])
    audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "CREATE"))
    assert audit.actor_user_id == admin["id"]
    assert audit.entity_id == stored_user.id
    assert audit.after_data == {"name": body["name"], "email": body["email"], "role": role, "is_active": True}


@pytest.mark.parametrize("role", [Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE])
def test_non_admin_cannot_create_accounts(client, session, role):
    headers = authorize(client, create_actor(session, role=role))
    assert client.post("/api/users", json=payload(), headers=headers).status_code == 403
    assert session.scalar(select(func.count()).select_from(User)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_public_registration_is_not_available(client):
    assert client.post("/api/users", json=payload()).status_code == 401


@pytest.mark.parametrize("headers", [{}, {"X-CSRF-TOKEN": "gresit"}])
def test_correct_csrf_is_required(client, session, headers):
    authorize(client, create_actor(session))
    assert client.post("/api/users", json=payload(), headers=headers).status_code == 401
    assert session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize("changes", [
    {"role": "ADMIN"}, {"role": "MANAGER"}, {"role": "warehouse"}, {"role": None},
    {"name": " "}, {"name": "a" * 121}, {"email": "invalid"},
    {"password": "scurta"}, {"password": "a" * 73}, {"password": "\u0103" * 37},
    {"password": 123}, {"is_active": False}, {"actor_user_id": 999},
])
def test_invalid_values_and_unapproved_fields_are_rejected(client, session, changes):
    headers = authorize(client, create_actor(session))
    assert client.post("/api/users", json=payload(**changes), headers=headers).status_code == 400
    assert session.scalar(select(func.count()).select_from(User)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_role_must_be_explicit(client, session):
    headers = authorize(client, create_actor(session))
    body = payload()
    del body["role"]
    assert client.post("/api/users", json=body, headers=headers).status_code == 400


def test_duplicate_normalized_email_returns_conflict_without_overwriting_account(client, session):
    admin = create_actor(session)
    headers = authorize(client, admin)
    response = client.post("/api/users", json=payload(email=f" {admin['email'].upper()} "), headers=headers)
    assert response.status_code == 409
    assert session.scalar(select(func.count()).select_from(User)) == 1
    assert session.get(User, admin["id"]).role == Role.ADMIN
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_audit_failure_rolls_back_account_creation(client, session, monkeypatch):
    headers = authorize(client, create_actor(session))

    def unavailable(**kwargs):
        raise SQLAlchemyError("detalii interne")

    monkeypatch.setattr(users, "record_audit", unavailable)
    response = client.post("/api/users", json=payload(), headers=headers)
    assert response.status_code == 503
    assert "detalii interne" not in response.get_data(as_text=True)
    assert session.scalar(select(func.count()).select_from(User)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_inactive_admin_cannot_create_accounts(client, session):
    headers = authorize(client, create_actor(session, active=False))
    assert client.post("/api/users", json=payload(), headers=headers).status_code == 401
    assert session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize("role,active", [(Role.DEPOZIT, True), (Role.ADMIN, False)])
def test_service_independently_checks_actor_permissions(session, role, active):
    actor = create_actor(session, role=role, active=active)
    with pytest.raises(users.UserCreationForbiddenError):
        users.create_team_user(actor_user_id=actor["id"], **payload())
    assert session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize("data,content_type,status", [
    ("{", "application/json", 400),
    ("name=Ana", "application/x-www-form-urlencoded", 415),
    ("a" * 5000, "application/json", 413),
])
def test_request_format_and_size_are_validated(client, session, data, content_type, status):
    headers = authorize(client, create_actor(session))
    response = client.post("/api/users", data=data, content_type=content_type, headers=headers)
    assert response.status_code == status
