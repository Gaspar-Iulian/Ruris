from uuid import uuid4

from flask import current_app
from flask_jwt_extended import create_access_token
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import limiter
from app.models import Role, User
from app.permissions import roles_required
from app.routes import users as user_routes


@pytest.fixture
def client(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    limiter.reset()

    @current_app.get("/api/test/purchases")
    @roles_required(Role.ACHIZITII)
    def purchases():
        return {"allowed": True}

    @current_app.get("/api/test/warehouse")
    @roles_required(Role.DEPOZIT)
    def warehouse():
        return {"allowed": True}

    @current_app.get("/api/test/invoices")
    @roles_required(Role.CONTABILITATE)
    def invoices():
        return {"allowed": True}

    @current_app.get("/api/test/catalog")
    @roles_required(Role.ACHIZITII, Role.DEPOZIT)
    def catalog():
        return {"allowed": True}

    return current_app.test_client()


def create_account(session, role, *, active=True):
    user = User(name="Utilizator test", email=f"role-{uuid4().hex}@example.com", role=role, is_active=active)
    user.set_password("parola-pentru-test-roluri")
    session.add(user)
    session.flush()
    values = {"id": user.id, "email": user.email, "token_version": user.token_version}
    session.commit()
    return values


def set_token(client, account, **extra_claims):
    token = create_access_token(
        identity=str(account["id"]),
        additional_claims={"token_version": account["token_version"], **extra_claims},
    )
    client.set_cookie("access_token_cookie", token, path="/api")


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("path,allowed_roles", [
    ("/api/users", {Role.ADMIN}),
    ("/api/test/purchases", {Role.ACHIZITII}),
    ("/api/test/warehouse", {Role.DEPOZIT}),
    ("/api/test/invoices", {Role.CONTABILITATE}),
    ("/api/test/catalog", {Role.ACHIZITII, Role.DEPOZIT}),
])
def test_role_matrix_enforces_explicit_permissions(client, session, role, path, allowed_roles):
    set_token(client, create_account(session, role))
    response = client.get(path)
    assert response.status_code == (200 if role in allowed_roles else 403)
    if role not in allowed_roles:
        assert response.get_json() == {"message": "Nu ai permisiunea necesara pentru aceasta operatie."}
        assert response.headers["Cache-Control"] == "no-store"


def test_missing_authentication_returns_401_instead_of_role_information(client):
    assert client.get("/api/users").status_code == 401


def test_role_claim_cannot_grant_administrator_access(client, session):
    set_token(client, create_account(session, Role.DEPOZIT), role="ADMIN")
    assert client.get("/api/users").status_code == 403


def test_role_change_is_effective_without_new_login(client, session):
    account = create_account(session, Role.ACHIZITII)
    set_token(client, account)
    assert client.get("/api/test/purchases").status_code == 200
    session.get(User, account["id"]).role = Role.DEPOZIT
    session.commit()
    assert client.get("/api/test/purchases").status_code == 403
    assert client.get("/api/test/warehouse").status_code == 200


def test_inactive_admin_cannot_access_user_list(client, session):
    set_token(client, create_account(session, Role.ADMIN, active=False))
    assert client.get("/api/users").status_code == 401


def test_user_list_is_paginated_and_does_not_expose_secrets(client, session):
    admin = create_account(session, Role.ADMIN)
    second = create_account(session, Role.CONTABILITATE, active=False)
    set_token(client, admin)
    first_response = client.get("/api/users?page=1&per_page=1")
    first = first_response.get_json()
    assert first_response.status_code == 200
    assert first_response.headers["Cache-Control"] == "no-store"
    assert first["pagination"] == {"page": 1, "per_page": 1, "total": 2, "pages": 2}
    assert first["users"][0]["id"] == admin["id"]
    assert set(first["users"][0]) == {"id", "name", "email", "role", "is_active"}
    last = client.get("/api/users?page=2&per_page=1").get_json()
    assert last["users"][0]["id"] == second["id"]
    assert last["users"][0]["is_active"] is False
    assert client.get("/api/users?page=3&per_page=1").get_json()["users"] == []


@pytest.mark.parametrize("query", [
    "page=0", "page=-1", "page=1000001", "page=abc", "per_page=0", "per_page=101",
    "role=ADMIN", "page=1&page=2",
])
def test_invalid_pagination_and_unsupported_filters_are_rejected(client, session, query):
    set_token(client, create_account(session, Role.ADMIN))
    assert client.get(f"/api/users?{query}").status_code == 400


def test_user_list_database_errors_do_not_leak_details(client, session, monkeypatch):
    set_token(client, create_account(session, Role.ADMIN))

    def unavailable(**kwargs):
        raise SQLAlchemyError("detalii interne")

    monkeypatch.setattr(user_routes, "list_users", unavailable)
    response = client.get("/api/users")
    assert response.status_code == 503
    assert "detalii interne" not in response.get_data(as_text=True)


def test_empty_role_policy_is_rejected():
    with pytest.raises(ValueError):
        roles_required()


def test_unknown_role_policy_is_rejected():
    with pytest.raises(ValueError):
        roles_required("MANAGER")
