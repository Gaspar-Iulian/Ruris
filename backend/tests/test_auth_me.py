from datetime import timedelta
from uuid import uuid4

from flask import current_app
from flask_jwt_extended import create_access_token
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import limiter
from app.models import Role, User
from app.services import auth


@pytest.fixture
def account(session):
    password = "parola-doar-pentru-test-me"
    user = User(name="Ana Test", email=f"ana-{uuid4().hex}@example.com", role=Role.DEPOZIT, is_active=True)
    user.set_password(password)
    session.add(user)
    session.flush()
    values = {"id": user.id, "email": user.email, "password": password, "token_version": user.token_version}
    session.commit()
    return values


@pytest.fixture
def client(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    limiter.reset()
    return current_app.test_client()


def sign_in(client, account):
    response = client.post("/api/auth/login", json={"email": account["email"], "password": account["password"]})
    assert response.status_code == 200


def set_token(client, identity, claims, expires_delta=None):
    token = create_access_token(identity=identity, additional_claims=claims, expires_delta=expires_delta)
    client.set_cookie("access_token_cookie", token, path="/api")


def test_me_returns_only_current_account_public_fields(client, account):
    sign_in(client, account)
    response = client.get("/api/auth/me?user_id=999")
    assert response.status_code == 200
    assert response.get_json() == {"user": {
        "id": account["id"], "name": "Ana Test", "email": account["email"], "role": "DEPOZIT",
    }}
    assert "Set-Cookie" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"


def test_me_requires_cookie(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.is_json
    assert "Set-Cookie" not in response.headers


def test_disabling_account_rejects_previously_valid_token(client, session, account):
    sign_in(client, account)
    session.get(User, account["id"]).is_active = False
    session.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_password_change_rejects_previous_token(client, session, account):
    sign_in(client, account)
    session.get(User, account["id"]).set_password("parola-noua-pentru-test")
    session.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_me_uses_current_role_instead_of_role_claim(client, session, account):
    set_token(client, str(account["id"]), {"token_version": account["token_version"], "role": "ADMIN"})
    assert client.get("/api/auth/me").get_json()["user"]["role"] == "DEPOZIT"
    session.get(User, account["id"]).role = Role.CONTABILITATE
    session.commit()
    assert client.get("/api/auth/me").get_json()["user"]["role"] == "CONTABILITATE"


def test_nonexistent_account_is_rejected(client):
    set_token(client, "9223372036854775807", {"token_version": 1})
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("identity", ["0", "-1", "07", "abc", "9" * 40, "\u0667"])
def test_invalid_identity_is_rejected_without_database_lookup(client, monkeypatch, identity):
    def unexpected_lookup(*args, **kwargs):
        raise AssertionError("Nu trebuie interogata baza pentru o identitate invalida.")

    monkeypatch.setattr(auth.db.session, "scalar", unexpected_lookup)
    set_token(client, identity, {"token_version": 1})
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("claims", [{}, {"token_version": "1"}, {"token_version": True}, {"token_version": -1}])
def test_invalid_or_missing_session_version_is_rejected(client, account, claims):
    set_token(client, str(account["id"]), claims)
    assert client.get("/api/auth/me").status_code == 401


def test_expired_token_is_rejected_before_account_lookup(client, account, monkeypatch):
    def unexpected_lookup(claims):
        raise AssertionError("Nu trebuie incarcat contul pentru un token expirat.")

    monkeypatch.setattr(auth, "get_authenticated_user", unexpected_lookup)
    set_token(client, str(account["id"]), {"token_version": account["token_version"]}, timedelta(seconds=-1))
    assert client.get("/api/auth/me").status_code == 401


def test_database_failure_returns_generic_error_without_clearing_cookie(client, account, monkeypatch):
    sign_in(client, account)

    def unavailable(claims):
        raise SQLAlchemyError("detalii interne")

    monkeypatch.setattr(auth, "get_authenticated_user", unavailable)
    response = client.get("/api/auth/me")
    assert response.status_code == 503
    assert response.is_json
    assert "detalii interne" not in response.get_data(as_text=True)
    assert response.headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in response.headers
