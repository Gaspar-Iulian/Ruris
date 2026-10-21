import importlib.util
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import current_app
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.extensions import db
from app.models import AuditEvent, Invoice, InvoiceAllocation, Role, User
from app.services.invoice_allocations import create_allocations, release_allocations
from app.services.invoices import InvoiceConflictError, create_invoice
from app.services.invoice_verification import approve_invoice, verify_invoice
from app.services.invoice_payments import record_payment
from test_invoice_allocations import payload, seed_data
from test_invoice_verification import cover


@pytest.mark.parametrize("operation", ["create", "release", "approve", "pay"])
def test_parallel_allocation_operations_do_not_duplicate_capacity(session, monkeypatch, operation):
    app = current_app._get_current_object()
    engine = db.engine
    schema = f"ruris_allocation_test_{uuid4().hex}"
    scoped = scoped_session(sessionmaker(bind=engine))
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
            migrations = Path(__file__).resolve().parents[1] / "migrations" / "versions"
            with Operations.context(MigrationContext.configure(connection)):
                for path in sorted(migrations.glob("0*.py")):
                    spec = importlib.util.spec_from_file_location(f"allocation_test_{path.stem}", path)
                    migration = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(migration)
                    migration.upgrade()
        with monkeypatch.context() as patcher:
            patcher.setattr(db, "session", scoped)
            # Keep the isolated schema selected across service commits.
            from sqlalchemy import event

            def use_schema(session, transaction, connection):
                connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})

            event.listen(scoped.session_factory, "after_begin", use_schema)
            data = seed_data(scoped)
            second = create_invoice(actor_user_id=data["users"][Role.CONTABILITATE], **{**data["data"], "number": "002"})
            other = User(name="Contabil 2", email="allocation-other@example.com", role=Role.CONTABILITATE,
                         password_hash="unused", token_version=1, is_active=True)
            scoped.add(other)
            scoped.flush()
            other_id = other.id
            scoped.commit()
            if operation == "release":
                initial = create_allocations(actor_user_id=data["users"][Role.CONTABILITATE],
                                             invoice_id=data["invoice"]["id"], **payload(data))
            elif operation in ("approve", "pay"):
                cover(data, scoped)
                verify_invoice(actor_user_id=data["users"][Role.CONTABILITATE], invoice_id=data["invoice"]["id"], version=2)
                if operation == "pay":
                    approve_invoice(actor_user_id=data["users"][Role.CONTABILITATE], invoice_id=data["invoice"]["id"], version=3, reason="Aprobare")
            barrier = Barrier(2)

            def worker(actor_id, invoice):
                with app.app_context():
                    try:
                        scoped.execute(text("SET LOCAL lock_timeout = '5s'"))
                        barrier.wait(timeout=10)
                        if operation == "create":
                            create_allocations(actor_user_id=actor_id, invoice_id=invoice["id"], **payload(data, invoice=invoice))
                        elif operation == "release":
                            release_allocations(actor_user_id=actor_id, invoice_id=data["invoice"]["id"], version=2,
                                                reason="Corectie concurenta", allocation_ids=[initial["allocations"][0]["id"]])
                        elif operation == "approve":
                            approve_invoice(actor_user_id=actor_id, invoice_id=data["invoice"]["id"], version=3, reason="Aprobare concurenta")
                        else:
                            record_payment(actor_user_id=actor_id, invoice_id=data["invoice"]["id"], version=4,
                                           reason="Plata concurenta", paid_at=datetime.now(timezone.utc).isoformat(), payment_reference="OP-1")
                        return "created"
                    except InvoiceConflictError:
                        return "conflict"
                    finally:
                        scoped.remove()

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(worker, data["users"][Role.CONTABILITATE], data["invoice"]),
                           executor.submit(worker, other_id, second)]
                assert sorted(future.result(timeout=15) for future in futures) == ["conflict", "created"]
            assert scoped.scalar(select(func.count()).select_from(InvoiceAllocation)) == 1
            assert scoped.scalar(select(func.sum(InvoiceAllocation.quantity))) == (6 if operation in ("approve", "pay") else 4)
            assert scoped.scalar(select(InvoiceAllocation.status)) == ("RELEASED" if operation == "release" else "ACTIVE")
            if operation == "approve":
                assert scoped.get(Invoice, data["invoice"]["id"]).status == "APPROVED"
                assert scoped.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "APPROVE")) == 1
            if operation == "pay":
                assert scoped.get(Invoice, data["invoice"]["id"]).status == "PAID"
                assert scoped.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "PAY")) == 1
    finally:
        scoped.remove()
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
