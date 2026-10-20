import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import current_app
from sqlalchemy import func, select, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.extensions import db
from app.models import AuditEvent, EmailAttempt, EmailOutbox, Role, User
from app.services.email_delivery import claim_delivery, queue_overdue_emails


def test_parallel_queue_and_claim_do_not_duplicate_daily_delivery(session, monkeypatch):
    app = current_app._get_current_object()
    engine = db.engine
    schema = f"ruris_email_test_{uuid4().hex}"
    scoped = scoped_session(sessionmaker(bind=engine))
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
            migrations = Path(__file__).resolve().parents[1] / "migrations" / "versions"
            with Operations.context(MigrationContext.configure(connection)):
                for path in sorted(migrations.glob("0*.py")):
                    spec = importlib.util.spec_from_file_location(f"email_test_{path.stem}", path)
                    migration = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(migration)
                    migration.upgrade()
        scoped.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
        user = User(name="Test", email="buyer@example.com", role=Role.ACHIZITII,
                    password_hash="unused", token_version=1, is_active=True)
        scoped.add(user)
        scoped.flush()
        user_id = user.id
        scoped.commit()
        message = {"recipient_user_id": user_id, "to": "buyer@example.com", "subject": "Test concurenta", "body": "Sumar"}
        digest = {"as_of": "2026-10-20", "messages": [message], "skipped_items": 0}
        barrier = Barrier(2)

        def worker(action):
            with app.app_context():
                try:
                    scoped.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
                    scoped.execute(text("SET LOCAL lock_timeout = '5s'"))
                    barrier.wait(timeout=10)
                    return action()
                finally:
                    scoped.remove()

        with monkeypatch.context() as patcher:
            patcher.setattr(db, "session", scoped)
            patcher.setattr("app.services.email_delivery.build_overdue_digests", lambda: digest)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(worker, lambda: queue_overdue_emails()["queued"]) for _ in range(2)]
                assert sorted(future.result(timeout=15) for future in futures) == [0, 1]
            scoped.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
            delivery_id = scoped.scalar(select(EmailOutbox.id))
            scoped.commit()
            barrier = Barrier(2)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(worker, lambda: claim_delivery(delivery_id, {user_id: message}) is not None) for _ in range(2)]
                assert sorted(future.result(timeout=15) for future in futures) == [False, True]
        scoped.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
        assert scoped.scalar(select(func.count()).select_from(EmailOutbox)) == 1
        assert scoped.scalar(select(func.count()).select_from(EmailAttempt)) == 1
        assert scoped.scalar(select(EmailOutbox.status)) == "SENDING"
        assert scoped.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "ENQUEUE")) == 1
        assert scoped.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "START")) == 1
    finally:
        scoped.remove()
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
