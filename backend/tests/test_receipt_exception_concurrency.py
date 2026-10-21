import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import current_app
import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.extensions import db
from app.models import ReceiptItem, Role, StockMovement, User
from app.services.receipt_exceptions import clarify_receipt_item, create_unordered_receipt, resolve_receipt_item
from app.services.receipts import ReceiptConflictError, confirm_receipt
from test_receipt_exceptions import seed_exceptions


@pytest.mark.parametrize("shared_receipt", [True, False])
def test_parallel_acceptances_share_receipt_and_order_limits(session, monkeypatch, shared_receipt):
    app = current_app._get_current_object()
    engine = db.engine
    schema = f"ruris_receipt_test_{uuid4().hex}"
    scoped = scoped_session(sessionmaker(bind=engine))
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
            with Operations.context(MigrationContext.configure(connection)):
                for path in sorted((Path(__file__).resolve().parents[1] / "migrations" / "versions").glob("0*.py")):
                    spec = importlib.util.spec_from_file_location(f"pending_test_{path.stem}", path)
                    migration = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(migration)
                    migration.upgrade()
        with monkeypatch.context() as patcher:
            patcher.setattr(db, "session", scoped)

            def use_schema(session, transaction, connection):
                connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})

            event.listen(scoped.session_factory, "after_begin", use_schema)
            data = seed_exceptions(scoped)
            other = User(name="Depozit 2", email="pending-other@example.com", role=Role.DEPOZIT,
                         password_hash="unused", token_version=1, is_active=True)
            scoped.add(other)
            scoped.flush()
            other_id = other.id
            scoped.commit()
            receipts = []
            for _ in range(1 if shared_receipt else 2):
                receipt = create_unordered_receipt(actor_user_id=data["users"][Role.DEPOZIT], supplier_id=data["supplier_id"],
                    delivery_reference="TEST", received_at="2026-10-21T08:00:00Z", items=[{
                        "product_id": data["product_id"], "description": "Marfa", "unit": "BUC", "received_quantity": "10"}])
                receipt = confirm_receipt(actor_user_id=data["users"][Role.DEPOZIT], receipt_id=receipt["id"], version=1, reason="Control", items=[{
                    "id": receipt["items"][0]["id"], "accepted_quantity": "0", "rejected_quantity": "0", "pending_quantity": "10"}])
                receipts.append(clarify_receipt_item(actor_user_id=data["users"][Role.ACHIZITII], receipt_id=receipt["id"],
                    item_id=receipt["items"][0]["id"], version=2, reason="Acoperire", purchase_order_item_id=data["order"]["items"][0]["id"]))
            barrier = Barrier(2)

            def worker(actor_id, receipt):
                with app.app_context():
                    try:
                        scoped.execute(text("SET LOCAL lock_timeout = '5s'"))
                        barrier.wait(timeout=10)
                        resolve_receipt_item(actor_user_id=actor_id, receipt_id=receipt["id"], item_id=receipt["items"][0]["id"],
                                             version=receipt["version"], reason="Decizie concurenta", action="ACCEPT", quantity="6")
                        return "accepted"
                    except ReceiptConflictError:
                        return "conflict"
                    finally:
                        scoped.remove()

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(worker, data["users"][Role.DEPOZIT], receipts[0]),
                           executor.submit(worker, other_id, receipts[-1])]
                assert sorted(future.result(timeout=15) for future in futures) == ["accepted", "conflict"]
            assert scoped.scalar(select(func.count()).select_from(StockMovement)) == 1
            assert scoped.scalar(select(func.sum(StockMovement.quantity_delta))) == 6
            assert scoped.scalar(select(func.sum(ReceiptItem.accepted_quantity))) == 6
            assert scoped.scalar(select(func.sum(ReceiptItem.resolved_quantity))) == 6
    finally:
        scoped.remove()
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
