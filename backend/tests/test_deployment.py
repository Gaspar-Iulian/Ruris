from contextlib import contextmanager
from unittest.mock import patch

from flask import request
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app import config
from app.extensions import db


@pytest.fixture
def deployment_settings(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda path: None)
    for key, value in {"POSTGRES_DB": "test", "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test-only",
                       "JWT_SECRET_KEY": "deployment-test-secret-" * 3, "BEHIND_PROXY": "false"}.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("enabled", [False, True])
def test_proxy_trust_is_explicit_and_does_not_replace_host(deployment_settings, monkeypatch, enabled):
    monkeypatch.setenv("BEHIND_PROXY", str(enabled).lower())
    app = create_app()

    @app.get("/proxy-test")
    def proxy_test():
        return {"address": request.remote_addr, "scheme": request.scheme, "host": request.host}

    response = app.test_client().get("/proxy-test", headers={"Host": "portal.local:8080", "X-Forwarded-For": "192.0.2.8",
        "X-Forwarded-Proto": "https", "X-Forwarded-Host": "untrusted.example"})
    assert response.json == {"address": "192.0.2.8" if enabled else "127.0.0.1", "scheme": "https" if enabled else "http",
                             "host": "portal.local:8080"}


def test_invalid_proxy_setting_prevents_startup(deployment_settings, monkeypatch):
    monkeypatch.setenv("BEHIND_PROXY", "maybe")
    with pytest.raises(RuntimeError, match="BEHIND_PROXY"):
        create_app()


@pytest.mark.parametrize("available", [True, False])
def test_readiness_checks_database_without_leaking_errors(deployment_settings, available):
    app = create_app()

    class Connection:
        def execute(self, statement):
            assert "alembic_version" in str(statement)

    @contextmanager
    def connect():
        if not available:
            raise SQLAlchemyError("private connection details")
        yield Connection()

    with app.app_context(), patch.object(db.engine, "connect", side_effect=connect):
        response = app.test_client().get("/api/ready")
    assert response.status_code == (200 if available else 503)
    assert response.json == {"status": "ready" if available else "unavailable"}
    assert response.headers["Cache-Control"] == "no-store"
