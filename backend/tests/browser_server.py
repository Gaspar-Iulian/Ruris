"""Serve real browser tests inside a rollback-only PostgreSQL transaction."""

import importlib.util
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import bcrypt
from flask import jsonify
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema
from werkzeug.serving import make_server

from app import create_app
from app.extensions import db
from app.models import Role, User


def main():
    app = create_app()
    app.config.update(JWT_COOKIE_SECURE=False, RATELIMIT_ENABLED=False)
    stopped = False

    @app.post("/__test__/stop")
    def stop():
        nonlocal stopped
        stopped = True
        return jsonify(stopped=True)

    with app.app_context():
        with db.engine.connect() as connection:
            transaction = connection.begin()
            test_session = Session(bind=connection, join_transaction_mode="create_savepoint")
            try:
                schema = "ruris_browser_" + uuid4().hex
                connection.execute(CreateSchema(schema))
                connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
                with Operations.context(MigrationContext.configure(connection)):
                    for path in sorted((Path(__file__).resolve().parents[1] / "migrations" / "versions").glob("0*.py")):
                        spec = importlib.util.spec_from_file_location(path.stem, path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        module.upgrade()
                with patch.object(db, "session", test_session):
                    test_session.remove = test_session.rollback
                    original_wsgi = app.wsgi_app

                    def request_context(environ, start_response):
                        # Use a fresh application context and close each request transaction.
                        with app.app_context():
                            return original_wsgi(environ, start_response)

                    app.wsgi_app = request_context
                    password = bcrypt.hashpw(b"Browser-test-2026!", bcrypt.gensalt(rounds=4)).decode("ascii")
                    for role in Role:
                        test_session.add(User(name=role.value, email=f"{role.value.lower()}@browser.example.com", password_hash=password, role=role, is_active=True, token_version=1))
                    test_session.commit()
                    with make_server("127.0.0.1", 5201, app, threaded=False) as server:
                        server.timeout = 1
                        print("Browser test server ready on 5201; all data will roll back.", flush=True)
                        while not stopped:
                            server.handle_request()
            finally:
                test_session.close()
                transaction.rollback()
                print("Browser test schema and data rolled back.", flush=True)


if __name__ == "__main__":
    main()
