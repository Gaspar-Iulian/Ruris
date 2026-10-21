import importlib.util
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema

from app import create_app
from app.extensions import db


@pytest.fixture
def session():
    if os.getenv("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Activeaza RUN_POSTGRES_TESTS=1 cu PostgreSQL pornit.")
    app = create_app()
    with app.app_context():
        assert db.engine.dialect.name == "postgresql"
        with db.engine.connect() as connection:
            transaction = connection.begin()
            test_session = Session(bind=connection, join_transaction_mode="create_savepoint")
            try:
                schema = f"ruris_test_{uuid4().hex}"
                connection.execute(CreateSchema(schema))
                connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
                migrations = Path(__file__).resolve().parents[1] / "migrations" / "versions"
                # Apply real migrations in a separate schema.
                with Operations.context(MigrationContext.configure(connection)):
                    for filename in (
                        "0001_users.py", "0002_audit_events.py", "0003_revoked_tokens.py",
                        "0004_romanian_roles.py", "0005_suppliers.py",
                        "0006_products.py",
                        "0007_purchase_orders.py",
                        "0008_receipts.py",
                        "0009_stock_movements.py",
                        "0010_email_delivery.py",
                        "0011_email_retry_schedule.py",
                        "0012_invoice_drafts_add_invoice_drafts.py",
                        "0013_invoice_line_order.py",
                        "0014_invoice_allocations_add_invoice_allocations.py",
                        "0015_invoice_verification_add_invoice_verification_issues.py",
                        "0016_exchange_rates_add_historical_exchange_rates.py",
                        "0017_invoice_approval_add_invoice_approval.py",
                        "0018_invoice_payment_add_invoice_payment_recording.py",
                        "0019_blocked_invoice_emails.py",
                        "0020_invoice_order_source.py",
                        "0021_receipt_exceptions.py",
                    ):
                        spec = importlib.util.spec_from_file_location(filename[:-3], migrations / filename)
                        migration = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(migration)
                        migration.upgrade()
                with patch.object(db, "session", test_session):
                    yield test_session
            finally:
                test_session.close()
                transaction.rollback()
