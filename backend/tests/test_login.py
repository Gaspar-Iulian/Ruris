import json
from uuid import uuid4

from flask import current_app
from flask_jwt_extended import decode_token
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import limiter
from app.models import AuditEvent, Role, User
from app.services import auth


@pytest.fixture
def client(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    limiter.reset()
    return current_app.test_client()


def create_account(session, *, active=True, password="parola-login-pentru-test"):
    user = User(
        name="Ana Test", email=f"ana-{uuid4().hex}@example.com",
        role=Role.ACHIZITII, is_active=active,
    )
    user.set_password(password)
    session.add(user)
    session.flush()
    values = {"id": user.id, "email": user.email, "password": password, "token_version": user.token_version}
    session.commit()
    return values


def login(client, account, **changes):
    body = {"email": account["email"], "password": account["password"]}
    body.update(changes)
    return client.post("/api/auth/login", json=body)


def test_login_issues_cookie_without_exposing_token_or_hash(client, session):
    account = create_account(session)
    response = login(client, account, email=f" {account['email'].upper()} ")
    assert response.status_code == 200
    body = response.get_json()
    assert body["user"] == {
        "id": account["id"], "name": "Ana Test", "email": account["email"], "role": "ACHIZITII",
    }
    assert "access_token" not in body
    assert "password_hash" not in response.get_data(as_text=True)
    cookie = client.get_cookie("access_token_cookie", path="/api")
    assert cookie.http_only
    claims = decode_token(cookie.value)
    assert claims["sub"] == str(account["id"])
    assert claims["token_version"] == account["token_version"]
    assert claims["fresh"] is True
    assert client.get_cookie("csrf_access_token") is not None
    assert response.headers["Cache-Control"] == "no-store"
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "LOGIN"))
    assert event.actor_user_id == account["id"]
    assert event.entity_id == account["id"]


def test_wrong_password_unknown_account_and_inactive_account_have_same_response(client, session):
    account = create_account(session, active=False)
    responses = [
        login(client, account, password="gresita"),
        login(client, account, email="necunoscut@example.com"),
        login(client, account),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.get_json() == {"message": "Email sau parola incorecta."}
        assert "Set-Cookie" not in response.headers
    events = session.scalars(select(AuditEvent).where(AuditEvent.action == "LOGIN_FAILED")).all()
    assert len(events) == 3
    assert all(event.actor_user_id is None and event.actor_process == "authentication" for event in events)
    assert all("password" not in json.dumps(event.after_data) for event in events)
    assert all(account["password"] not in json.dumps(event.after_data) for event in events)


def test_password_whitespace_is_significant(client, session):
    account = create_account(session, password=" parola-cu-spatii ")
    assert login(client, account, password=account["password"].strip()).status_code == 401
    assert login(client, account).status_code == 200


@pytest.mark.parametrize("body", [
    {}, [], {"email": "ana@example.com"},
    {"email": None, "password": "parola"},
    {"email": "ana@example.com", "password": 123},
    {"email": " ", "password": "parola"},
    {"email": "ana@example.com", "password": ""},
    {"email": "ana@example.com", "password": "parola", "role": "ADMIN"},
])
def test_invalid_payload_is_rejected_without_cookie(client, body):
    response = client.post("/api/auth/login", json=body)
    assert response.status_code == 400
    assert "Set-Cookie" not in response.headers


def test_form_submission_is_not_accepted_as_login(client):
    response = client.post("/api/auth/login", data={"email": "ana@example.com", "password": "test"})
    assert response.status_code == 415


def test_malformed_json_is_rejected(client):
    response = client.post("/api/auth/login", data="{", content_type="application/json")
    assert response.status_code == 400
    assert response.is_json


def test_oversized_body_is_rejected(client):
    response = client.post("/api/auth/login", json={"email": "ana@example.com", "password": "a" * 5000})
    assert response.status_code == 413


@pytest.mark.parametrize("headers", [{"Origin": "https://alt-site.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}])
def test_cross_origin_login_is_rejected(client, headers):
    response = client.post("/api/auth/login", json={"email": "ana@example.com", "password": "test"}, headers=headers)
    assert response.status_code == 403
    assert "Set-Cookie" not in response.headers


def test_same_origin_browser_login_is_allowed(client, session):
    account = create_account(session)
    response = client.post(
        "/api/auth/login", json={"email": account["email"], "password": account["password"]},
        headers={"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 200


def test_failed_attempts_are_rate_limited_and_forwarded_ip_is_not_trusted(client):
    for _ in range(10):
        response = client.post("/api/auth/login", json={"email": "necunoscut@example.com", "password": "gresita"})
        assert response.status_code == 401
    response = client.post(
        "/api/auth/login", json={"email": "necunoscut@example.com", "password": "gresita"},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert response.status_code == 429
    assert response.is_json
    assert "Retry-After" in response.headers


def test_audit_failure_prevents_token_cookie(client, session, monkeypatch):
    account = create_account(session)

    def fail_audit(**kwargs):
        raise SQLAlchemyError("eroare interna care nu trebuie afisata")

    monkeypatch.setattr(auth, "record_audit", fail_audit)
    response = login(client, account)
    assert response.status_code == 503
    assert "Set-Cookie" not in response.headers
    assert "eroare interna" not in response.get_data(as_text=True)
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_get_cannot_be_used_to_submit_credentials(client):
    assert client.get("/api/auth/login").status_code == 405
