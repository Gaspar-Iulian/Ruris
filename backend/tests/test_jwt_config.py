from datetime import timedelta

from flask import jsonify
from flask_jwt_extended import create_access_token, decode_token, get_csrf_token
from flask_jwt_extended import get_jwt_identity, jwt_required, set_access_cookies
import pytest

from app import create_app
from app import config
from app.models import User
from app.services import auth


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda path: None)
    for key, value in {
        "POSTGRES_DB": "test", "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test-only",
        "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": "5432",
        "JWT_SECRET_KEY": "test-only-jwt-secret-" * 3,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("JWT_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("JWT_ACCESS_TOKEN_MINUTES", raising=False)


@pytest.fixture
def jwt_app(settings, monkeypatch):
    monkeypatch.setenv("JWT_COOKIE_SECURE", "false")
    # These tests isolate token and cookie behavior from account lookup.
    monkeypatch.setattr(auth, "get_authenticated_user", lambda claims: User(id=7))
    monkeypatch.setattr(auth, "is_token_revoked", lambda claims: False)
    app = create_app()
    app.config["TESTING"] = True

    @app.route("/api/test/protected", methods=["GET", "POST"])
    @jwt_required()
    def protected():
        return {"user_id": get_jwt_identity()}

    return app


def make_token(app, expires_delta=None):
    with app.app_context():
        token = create_access_token(identity="7", expires_delta=expires_delta)
        return token, get_csrf_token(token)


@pytest.mark.parametrize("secret", [None, "", "prea-scurta", " " * 64])
def test_missing_or_short_secret_prevents_startup(settings, monkeypatch, secret):
    if secret is None:
        monkeypatch.delenv("JWT_SECRET_KEY")
    else:
        monkeypatch.setenv("JWT_SECRET_KEY", secret)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_app()


@pytest.mark.parametrize("minutes", ["0", "-1", "61", "fara-expirare"])
def test_invalid_token_duration_is_rejected(settings, monkeypatch, minutes):
    monkeypatch.setenv("JWT_ACCESS_TOKEN_MINUTES", minutes)
    with pytest.raises(RuntimeError, match="JWT_ACCESS_TOKEN_MINUTES"):
        config.get_config()


def test_invalid_secure_cookie_setting_is_rejected(settings, monkeypatch):
    monkeypatch.setenv("JWT_COOKIE_SECURE", "gresit")
    with pytest.raises(RuntimeError, match="JWT_COOKIE_SECURE"):
        config.get_config()


def test_token_uses_configured_lifetime(settings, monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TOKEN_MINUTES", "10")
    app = create_app()
    with app.app_context():
        claims = decode_token(create_access_token(identity="7"))
    assert claims["exp"] - claims["iat"] == 600


def test_token_cookie_is_http_only_and_secure_by_default(settings):
    app = create_app()
    with app.app_context():
        response = jsonify({"status": "ok"})
        set_access_cookies(response, create_access_token(identity="7"))
    cookies = response.headers.getlist("Set-Cookie")
    token_cookie = next(cookie for cookie in cookies if cookie.startswith("access_token_cookie="))
    csrf_cookie = next(cookie for cookie in cookies if cookie.startswith("csrf_access_token="))
    assert "HttpOnly" in token_cookie
    assert "Secure" in token_cookie
    assert "SameSite=Lax" in token_cookie
    assert "Path=/api" in token_cookie
    assert "HttpOnly" not in csrf_cookie


def test_request_without_token_is_rejected(jwt_app):
    assert jwt_app.test_client().get("/api/test/protected").status_code == 401


def test_token_in_header_does_not_replace_cookie(jwt_app):
    token, _ = make_token(jwt_app)
    response = jwt_app.test_client().get(
        "/api/test/protected", headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_cookie_allows_read_but_changes_require_correct_csrf_header(jwt_app):
    token, csrf = make_token(jwt_app)
    client = jwt_app.test_client()
    client.set_cookie("access_token_cookie", token, path="/api")
    response = client.get("/api/test/protected")
    assert response.status_code == 200
    assert response.get_json() == {"user_id": "7"}
    assert client.post("/api/test/protected").status_code == 401
    assert client.post("/api/test/protected", headers={"X-CSRF-TOKEN": "gresit"}).status_code == 401
    assert client.post("/api/test/protected", headers={"X-CSRF-TOKEN": csrf}).status_code == 200


def test_expired_token_is_rejected(jwt_app):
    with jwt_app.app_context():
        token = create_access_token(identity="7", expires_delta=timedelta(seconds=-1))
    client = jwt_app.test_client()
    client.set_cookie("access_token_cookie", token, path="/api")
    assert client.get("/api/test/protected").status_code == 401


def test_altered_signature_is_rejected(jwt_app):
    token, _ = make_token(jwt_app)
    header, payload, signature = token.split(".")
    signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    client = jwt_app.test_client()
    client.set_cookie("access_token_cookie", f"{header}.{payload}.{signature}", path="/api")
    assert client.get("/api/test/protected").status_code == 401


def test_health_remains_public(jwt_app):
    response = jwt_app.test_client().get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
