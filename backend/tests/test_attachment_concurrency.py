import importlib.util
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
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
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import Attachment, AuditEvent, Invoice, Role, User
from app.services.attachments import AttachmentConflict, upload_attachment
from app.services.invoice_verification import approve_invoice, verify_invoice
from app.services.invoices import InvoiceConflictError
from test_attachments import PDF
from test_invoice_allocations import seed_data
from test_invoice_verification import cover


@pytest.mark.parametrize("scenario", ["same_key", "two_uploads", "upload_and_approval"])
def test_parallel_document_operations_preserve_files_versions_and_approval(session, monkeypatch, tmp_path, scenario):
    app = current_app._get_current_object()
    app.config["ATTACHMENT_STORAGE_PATH"] = str(tmp_path / "files")
    engine = db.engine
    schema = "ruris_attachment_test_" + uuid4().hex
    scoped = scoped_session(sessionmaker(bind=engine))
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
            migrations = Path(__file__).resolve().parents[1] / "migrations" / "versions"
            with Operations.context(MigrationContext.configure(connection)):
                for path in sorted(migrations.glob("0*.py")):
                    spec = importlib.util.spec_from_file_location(f"attachment_test_{path.stem}", path)
                    migration = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(migration)
                    migration.upgrade()
        with monkeypatch.context() as patcher:
            patcher.setattr(db, "session", scoped)

            def use_schema(session, transaction, connection):
                connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})

            event.listen(scoped.session_factory, "after_begin", use_schema)
            data = seed_data(scoped)
            other = User(name="Contabil 2", email="attachment-other@example.com", role=Role.CONTABILITATE,
                         password_hash="unused", token_version=1, is_active=True)
            scoped.add(other)
            scoped.flush()
            other_id = other.id
            scoped.commit()
            version = 1
            if scenario == "upload_and_approval":
                cover(data, scoped)
                verify_invoice(actor_user_id=data["users"][Role.CONTABILITATE], invoice_id=data["invoice"]["id"], version=2)
                version = 3
            barrier = Barrier(2)
            key = str(uuid4())

            def worker(index):
                with app.app_context():
                    try:
                        scoped.execute(text("SET LOCAL lock_timeout = '5s'"))
                        barrier.wait(timeout=10)
                        actor = data["users"][Role.CONTABILITATE] if index == 0 or scenario == "same_key" else other_id
                        if scenario == "upload_and_approval" and index == 1:
                            approve_invoice(actor_user_id=actor, invoice_id=data["invoice"]["id"], version=version, reason="Control final")
                            return "approved"
                        result = upload_attachment(actor_user_id=actor, kind="invoices", document_id=data["invoice"]["id"],
                            version=version, reason="Document justificativ", upload_key=key if scenario == "same_key" else str(uuid4()),
                            upload=FileStorage(stream=BytesIO(PDF), filename="factura.pdf", content_type="application/pdf"))
                        return "replayed" if result["replayed"] else "uploaded"
                    except (AttachmentConflict, InvoiceConflictError):
                        return "conflict"
                    finally:
                        scoped.remove()

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(worker, index) for index in (0, 1)]
                outcomes = [future.result(timeout=20) for future in futures]
            if scenario == "same_key":
                assert sorted(outcomes) == ["replayed", "uploaded"]
            else:
                assert outcomes.count("conflict") == 1
            count = scoped.scalar(select(func.count()).select_from(Attachment))
            assert count == (0 if "approved" in outcomes else 1)
            assert scoped.get(Invoice, data["invoice"]["id"]).version == version + 1
            assert scoped.get(Invoice, data["invoice"]["id"]).status == ("APPROVED" if "approved" in outcomes else "DRAFT")
            assert scoped.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "attachments", AuditEvent.action == "UPLOAD")) == count
            objects = tmp_path / "files" / "objects"
            assert (len(list(objects.iterdir())) if objects.exists() else 0) == count
            staging = tmp_path / "files" / "staging"
            assert not staging.exists() or not list(staging.iterdir())
    finally:
        scoped.remove()
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
