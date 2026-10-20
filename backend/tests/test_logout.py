from uuid import UUID, uuid4

from flask import current_app
from flask_jwt_extended import create_access_token, decode_token
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import limiter
from app.models import AuditEvent, RevokedToken, Role, User
from app.services import auth


@pytest.fixture
def account(session):
    password = "parola-pentru-test-logout"
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
    return client.get_cookie("access_token_cookie", path="/api").value, client.get_cookie("csrf_access_token").value


def test_logout_revokes_token_clears_cookies_and_records_audit(client, session, account):
    old_token, csrf = sign_in(client, account)
    response = client.post("/api/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    assert response.status_code == 200
    assert response.get_json() == {"message": "Deconectare reusita."}
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get_cookie("access_token_cookie", path="/api") is None
    assert client.get_cookie("csrf_access_token") is None
    assert client.get("/api/auth/me").status_code == 401
    replay_client = current_app.test_client()
    replay_client.set_cookie("access_token_cookie", old_token, path="/api")
    assert replay_client.get("/api/auth/me").status_code == 401
    revoked = session.scalar(select(RevokedToken))
    assert revoked.token_jti == UUID(decode_token(old_token)["jti"])
    assert revoked.user_id == account["id"]
    assert int(revoked.expires_at.timestamp()) == decode_token(old_token)["exp"]
    assert revoked.revoked_at.utcoffset() is not None
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "LOGOUT"))
    assert event.actor_user_id == account["id"]
    assert event.entity_id == account["id"]
    assert event.after_data is None


@pytest.mark.parametrize("headers", [{}, {"X-CSRF-TOKEN": "gresit"}])
def test_logout_without_correct_csrf_does_not_revoke_token(client, session, account, headers):
    sign_in(client, account)
    response = client.post("/api/auth/logout", headers=headers)
    assert response.status_code == 401
    assert "Set-Cookie" not in response.headers
    assert client.get("/api/auth/me").status_code == 200
    assert session.scalar(select(func.count()).select_from(RevokedToken)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "LOGOUT")) == 0


def test_logout_requires_authentication(client):
    assert client.post("/api/auth/logout").status_code == 401


def test_get_does_not_log_out_user(client, account):
    sign_in(client, account)
    assert client.get("/api/auth/logout").status_code == 405
    assert client.get("/api/auth/me").status_code == 200


def test_audit_failure_rolls_back_revocation_and_preserves_cookies(client, session, account, monkeypatch):
    token, csrf = sign_in(client, account)

    def unavailable(**kwargs):
        raise SQLAlchemyError("eroare interna")

    monkeypatch.setattr(auth, "record_audit", unavailable)
    response = client.post("/api/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    assert response.status_code == 503
    assert "Set-Cookie" not in response.headers
    assert "eroare interna" not in response.get_data(as_text=True)
    assert client.get_cookie("access_token_cookie", path="/api").value == token
    assert client.get("/api/auth/me").status_code == 200
    assert session.scalar(select(func.count()).select_from(RevokedToken)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "LOGOUT")) == 0


def test_failed_revocation_check_denies_access_without_clearing_cookie(client, account, monkeypatch):
    _, csrf = sign_in(client, account)

    def unavailable(claims):
        raise SQLAlchemyError("detalii interne")

    monkeypatch.setattr(auth, "is_token_revoked", unavailable)
    response = client.post("/api/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    assert response.status_code == 503
    assert "Set-Cookie" not in response.headers
    assert "detalii interne" not in response.get_data(as_text=True)


def test_logout_only_revokes_current_session(client, session, account):
    _, csrf = sign_in(client, account)
    other_client = current_app.test_client()
    sign_in(other_client, account)
    assert client.post("/api/auth/logout", headers={"X-CSRF-TOKEN": csrf}).status_code == 200
    assert other_client.get("/api/auth/me").status_code == 200
    assert session.get(User, account["id"]).token_version == account["token_version"]
    assert session.scalar(select(func.count()).select_from(RevokedToken)) == 1


def test_new_login_after_logout_creates_valid_session(client, account):
    old_token, csrf = sign_in(client, account)
    assert client.post("/api/auth/logout", headers={"X-CSRF-TOKEN": csrf}).status_code == 200
    new_token, _ = sign_in(client, account)
    assert new_token != old_token
    assert client.get("/api/auth/me").status_code == 200


def test_replaying_logout_with_revoked_token_is_rejected(client, session, account):
    token, csrf = sign_in(client, account)
    assert client.post("/api/auth/logout", headers={"X-CSRF-TOKEN": csrf}).status_code == 200
    client.set_cookie("access_token_cookie", token, path="/api")
    assert client.post("/api/auth/logout", headers={"X-CSRF-TOKEN": csrf}).status_code == 401
    assert session.scalar(select(func.count()).select_from(RevokedToken)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "LOGOUT")) == 1


def test_duplicate_revocation_does_not_duplicate_audit(client, session, account):
    token, _ = sign_in(client, account)
    claims = decode_token(token)
    auth.revoke_token(user_id=account["id"], claims=claims)
    auth.revoke_token(user_id=account["id"], claims=claims)
    assert session.scalar(select(func.count()).select_from(RevokedToken)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "LOGOUT")) == 1


@pytest.mark.parametrize("jti", ["invalid", "g" * 36, {}])
def test_invalid_token_identifier_is_rejected_without_database_query(client, account, monkeypatch, jti):
    token = create_access_token(
        identity=str(account["id"]), additional_claims={"token_version": account["token_version"], "jti": jti},
    )
    client.set_cookie("access_token_cookie", token, path="/api")

    def unexpected_query(*args, **kwargs):
        raise AssertionError("Invalid identifiers must not reach PostgreSQL.")

    monkeypatch.setattr(auth.db.session, "scalar", unexpected_query)
    assert client.get("/api/auth/me").status_code == 401


def test_token_without_expiration_is_not_accepted(client, account):
    token = create_access_token(
        identity=str(account["id"]), additional_claims={"token_version": account["token_version"]},
        expires_delta=False,
    )
    client.set_cookie("access_token_cookie", token, path="/api")
    assert client.get("/api/auth/me").status_code == 401
