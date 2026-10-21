"""Serve real browser tests inside a rollback-only PostgreSQL transaction."""

import importlib.util
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from tempfile import TemporaryDirectory, gettempdir

from alembic.migration import MigrationContext
from alembic.operations import Operations
import bcrypt
from flask import jsonify, request
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema
from werkzeug.serving import make_server

from app import create_app
from app.extensions import db
from app.models import Role, User
from app.services.exchange_rates import ExchangeRateUnavailable
from mailpit_config import configure_test_mailpit


def main():
    app = create_app()
    app.config.update(JWT_COOKIE_SECURE=False, RATELIMIT_ENABLED=False)
    configure_test_mailpit(app)
    stopped = False
    fx_mode = "fixture"

    def exchange_fixture(year):
        if fx_mode == "unavailable":
            raise ExchangeRateUnavailable("Simulated network outage")
        # Keep browser tests independent of the public network.
        cubes = ''.join(f'<Cube date="{day}"><Rate currency="EUR">5.1234</Rate></Cube>' for day in ("2026-10-20", "2026-10-21"))
        data = f'<DataSet xmlns="https://www.bnr.ro/xsd"><Header><Publisher>National Bank of Romania</Publisher></Header><Body><OrigCurrency>RON</OrigCurrency>{cubes}</Body></DataSet>'.encode()
        return f"https://curs.bnr.ro/files/xml/years/nbrfxrates{year}.xml", data

    @app.post("/__test__/fx")
    def configure_fx():
        nonlocal fx_mode
        mode = request.get_json()["mode"]
        if mode not in ("fixture", "unavailable"):
            return jsonify(message="Invalid fixture mode"), 400
        fx_mode = mode
        return jsonify(mode=fx_mode)

    @app.post("/__test__/stop")
    def stop():
        nonlocal stopped
        stopped = True
        return jsonify(stopped=True)

    @app.post("/__test__/notifications")
    def notifications():
        from app.services.email_delivery import send_notification_digests_local
        return jsonify(send_notification_digests_local())

    with TemporaryDirectory(prefix="ruris_browser_files_") as storage_directory, app.app_context():
        assert Path(storage_directory).resolve().is_relative_to(Path(gettempdir()).resolve())
        app.config["ATTACHMENT_STORAGE_PATH"] = storage_directory
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
                with patch.object(db, "session", test_session), patch("app.services.exchange_rates.download_year", exchange_fixture):
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
                        print(f"Automated emails use the separate test inbox on {app.config['MAILPIT_TEST_UI_PORT']}.", flush=True)
                        while not stopped:
                            server.handle_request()
            finally:
                test_session.close()
                transaction.rollback()
                print("Browser test schema and data rolled back.", flush=True)


if __name__ == "__main__":
    main()
