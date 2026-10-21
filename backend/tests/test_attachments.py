from base64 import b64decode
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from flask import current_app
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.models import Attachment, AuditEvent, Invoice, InvoiceAllocation, PurchaseOrderItem, ReceiptItem, Role, User
from app import create_app
from app.services.attachment_storage import MAX_FILE_BYTES, file_name
from app.services.attachments import check_attachment_storage
from app.services.invoices import get_invoice
from app.services.purchase_orders import get_order
from app.services.receipts import create_receipt
from test_invoice_allocations import authorize, setup
from test_invoice_verification import cover, verify


PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


@pytest.fixture
def storage(setup, tmp_path):
    current_app.config["ATTACHMENT_STORAGE_PATH"] = str(tmp_path / "attachments")
    return tmp_path / "attachments"


def parent(setup, session, kind):
    if kind == "invoices":
        return get_invoice(setup["invoice"]["id"])
    if kind == "receipts":
        return setup["receipt"]
    received = session.get(ReceiptItem, setup["receipt"]["items"][0]["id"])
    ordered = session.get(PurchaseOrderItem, received.purchase_order_item_id)
    return get_order(ordered.purchase_order_id)


def endpoint(kind, document_id):
    return f"/api/documents/{kind}/{document_id}/attachments"


def upload(setup, document, *, kind="invoices", role=Role.CONTABILITATE, content=PDF, name="factură.pdf", mime="application/pdf", version=None, key=None, reason="Document primit de la furnizor"):
    client, headers = authorize(setup["users"][role])
    return client.post(endpoint(kind, document["id"]), headers=headers, data={
        "file": (BytesIO(content), name, mime), "version": str(version if version is not None else document["version"]),
        "reason": reason, "upload_key": key or str(uuid4())})


@pytest.mark.parametrize("kind,writer", [("orders", Role.ACHIZITII), ("receipts", Role.DEPOZIT), ("invoices", Role.CONTABILITATE)])
def test_upload_and_download_keep_exact_bytes_private_paths_and_audit(setup, session, storage, kind, writer):
    document = parent(setup, session, kind)
    response = upload(setup, document, kind=kind, role=writer)
    assert response.status_code == 201, response.json
    result = response.json
    record = result["attachment"]
    assert result["document"]["version"] == document["version"] + 1
    assert record["original_name"] == "factură.pdf"
    assert record["content_sha256"] == sha256(PDF).hexdigest()
    assert "storage_key" not in str(result) and "upload_key" not in str(result)
    client, _ = authorize(setup["users"][writer])
    listed = client.get(endpoint(kind, document["id"]))
    assert listed.json["attachments"][0]["id"] == record["id"]
    assert listed.headers["Cache-Control"] == "no-store"
    downloaded = client.get(f'/api/attachments/{record["id"]}/download')
    assert downloaded.status_code == 200
    assert downloaded.data == PDF
    assert downloaded.mimetype == "application/pdf"
    assert downloaded.headers["Content-Disposition"].startswith("attachment;")
    assert downloaded.headers["X-Content-Type-Options"] == "nosniff"
    assert downloaded.headers["Cache-Control"] == "no-store"
    events = session.scalars(select(AuditEvent).where(AuditEvent.entity_type == "attachments").order_by(AuditEvent.id)).all()
    assert [event.action for event in events] == ["UPLOAD", "DOWNLOAD"]
    assert events[0].actor_user_id == setup["users"][writer]
    assert events[0].after_data["content_sha256"] == sha256(PDF).hexdigest()
    assert check_attachment_storage() == {"referenced": 1, "missing_or_corrupted": 0, "unreferenced": 0, "staged": 0}


@pytest.mark.parametrize("kind,writer,readers", [
    ("orders", Role.ACHIZITII, {Role.ACHIZITII, Role.CONTABILITATE}),
    ("receipts", Role.DEPOZIT, {Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE}),
    ("invoices", Role.CONTABILITATE, {Role.CONTABILITATE}),
])
def test_role_matrix_enforced_on_list_download_upload_and_withdraw(setup, session, storage, kind, writer, readers):
    document = parent(setup, session, kind)
    result = upload(setup, document, kind=kind, role=writer).json
    file_id = result["attachment"]["id"]
    for role in Role:
        client, headers = authorize(setup["users"][role])
        expected = 200 if role in readers else 403
        assert client.get(endpoint(kind, document["id"])).status_code == expected
        assert client.get(f"/api/attachments/{file_id}/download").status_code == expected
        if role != writer:
            assert upload(setup, result["document"], kind=kind, role=role).status_code == 403
            assert client.post(f"/api/attachments/{file_id}/withdraw", headers=headers,
                json={"version": result["document"]["version"], "reason": "Nu este permis"}).status_code == 403


def test_withdrawal_retains_bytes_and_history_and_cannot_be_reversed(setup, session, storage):
    result = upload(setup, setup["invoice"]).json
    file_id = result["attachment"]["id"]
    client, headers = authorize(setup["users"][Role.CONTABILITATE])
    response = client.post(f"/api/attachments/{file_id}/withdraw", headers=headers,
        json={"version": result["document"]["version"], "reason": "Versiune gresita de document"})
    assert response.status_code == 200, response.json
    assert response.json["attachment"]["status"] == "WITHDRAWN"
    assert response.json["document"]["version"] == result["document"]["version"] + 1
    assert client.get(f"/api/attachments/{file_id}/download").data == PDF
    listed = client.get(endpoint("invoices", setup["invoice"]["id"])).json
    assert listed["attachments"][0]["withdrawal_reason"] == "Versiune gresita de document"
    for statement in ("DELETE FROM attachments WHERE id = :id", "UPDATE attachments SET status = 'ACTIVE', withdrawn_at = NULL, withdrawn_by_id = NULL, withdrawal_reason = NULL WHERE id = :id",
            "UPDATE attachments SET withdrawal_reason = 'Other reason' WHERE id = :id"):
        with pytest.raises(DBAPIError), session.begin_nested():
            session.execute(text(statement), {"id": file_id})
    assert check_attachment_storage()["referenced"] == 1


def test_invoice_attachment_invalidates_verification_and_approved_documents_are_read_only(setup, session, storage):
    cover(setup, session)
    verified = verify(setup, 2).json["invoice"]
    assert verified["status"] == "VERIFIED"
    result = upload(setup, verified).json
    assert result["document"]["status"] == "DRAFT"
    assert result["document"]["total_ron"] is None
    assert session.scalar(select(InvoiceAllocation.status)) == "ACTIVE"
    reverified = verify(setup, 4).json["invoice"]
    assert reverified["status"] == "VERIFIED"
    client, headers = authorize(setup["users"][Role.CONTABILITATE])
    approved = client.post(f'/api/invoices/{verified["id"]}/approve', headers=headers, json={"version": 5, "reason": "Document verificat"}).json["invoice"]
    assert upload(setup, approved).status_code == 409
    assert client.post(f'/api/attachments/{result["attachment"]["id"]}/withdraw', headers=headers,
        json={"version": approved["version"], "reason": "Prea tarziu"}).status_code == 409
    assert client.get(f'/api/attachments/{result["attachment"]["id"]}/download').status_code == 200


def test_same_upload_key_replays_without_extra_file_or_audit_and_rejects_other_content(setup, session, storage):
    key = str(uuid4())
    first = upload(setup, setup["invoice"], key=key)
    second = upload(setup, setup["invoice"], key=key)
    assert first.status_code == 201 and second.status_code == 200
    assert second.json["replayed"] is True
    assert first.json["attachment"]["id"] == second.json["attachment"]["id"]
    assert upload(setup, setup["invoice"], key=key, reason="Alta utilizare").status_code == 409
    assert session.scalar(select(func.count()).select_from(Attachment)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "attachments")) == 1
    assert len(list((storage / "objects").iterdir())) == 1


@pytest.mark.parametrize("content,name,mime", [
    (b"", "factura.pdf", "application/pdf"), (b"<script>bad()</script>", "factura.pdf", "application/pdf"),
    (PDF, "factura.exe", "application/pdf"), (PDF, "factura.pdf", "image/png"),
    (PNG, "factura.pdf", "application/pdf"), (PDF, "../factura.pdf", "application/pdf"),
    (PDF[:-8], "factura.pdf", "application/pdf"), (b"\x89PNG\r\n\x1a\n", "foto.png", "image/png"),
])
def test_invalid_file_creates_neither_metadata_nor_persistent_files(setup, session, storage, content, name, mime):
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    response = upload(setup, setup["invoice"], content=content, name=name, mime=mime)
    assert response.status_code == 400, response.json
    assert session.scalar(select(func.count()).select_from(Attachment)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
    assert list(storage.rglob("*")) == [] or not any(path.is_file() for path in storage.rglob("*"))


def test_png_and_exact_size_limit(setup, session, storage):
    response = upload(setup, setup["receipt"], kind="receipts", role=Role.DEPOZIT, content=PNG, name="foto.png", mime="image/png")
    assert response.status_code == 201, response.json
    prefix, suffix = b"%PDF-1.4\n%", b"\n%%EOF\n"
    at_limit = prefix + b"A" * (MAX_FILE_BYTES - len(prefix) - len(suffix)) + suffix
    assert upload(setup, setup["invoice"], content=at_limit).status_code == 201
    current = get_invoice(setup["invoice"]["id"])
    assert upload(setup, current, content=at_limit + b" ").status_code == 413
    assert upload(setup, current, content=at_limit + b" " * 100000).status_code == 413


def test_audit_failure_rolls_back_metadata_version_and_published_file(setup, session, storage, monkeypatch):
    def fail(**kwargs):
        raise ValueError("Audit unavailable")
    monkeypatch.setattr("app.services.attachments.record_audit", fail)
    response = upload(setup, setup["invoice"])
    assert response.status_code == 400
    assert session.scalar(select(func.count()).select_from(Attachment)) == 0
    assert get_invoice(setup["invoice"]["id"])["version"] == 1
    assert not any(path.is_file() for path in storage.rglob("*"))


def test_uncertain_commit_retains_the_file_and_retry_is_idempotent(setup, session, storage, monkeypatch):
    original_commit = session.commit
    key = str(uuid4())
    def uncertain_commit():
        original_commit()
        raise SQLAlchemyError("Connection lost after commit")
    with monkeypatch.context() as patcher:
        patcher.setattr(session, "commit", uncertain_commit)
        response = upload(setup, setup["invoice"], key=key)
    assert response.status_code == 503
    assert session.scalar(select(func.count()).select_from(Attachment)) == 1
    assert check_attachment_storage()["missing_or_corrupted"] == 0
    replay = upload(setup, setup["invoice"], key=key)
    assert replay.status_code == 200 and replay.json["replayed"]
    assert len(list((storage / "objects").iterdir())) == 1


def test_corruption_prevents_download_and_storage_check_reports_it(setup, session, storage):
    result = upload(setup, setup["invoice"]).json
    record = session.get(Attachment, result["attachment"]["id"])
    (storage / "objects" / record.storage_key).write_bytes(b"Changed content")
    client, _ = authorize(setup["users"][Role.CONTABILITATE])
    assert client.get(f"/api/attachments/{record.id}/download").status_code == 503
    assert check_attachment_storage()["missing_or_corrupted"] == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "attachments", AuditEvent.action == "DOWNLOAD")) == 0


def test_warehouse_cannot_discover_commercial_files_in_order_history(setup, session, storage):
    order = parent(setup, session, "orders")
    result = upload(setup, order, kind="orders", role=Role.ACHIZITII, name="Pret-confidential-98765.pdf").json
    client, _ = authorize(setup["users"][Role.DEPOZIT])
    history = client.get(f'/api/purchase-orders/{order["id"]}/history').json
    assert "98765" not in str(history) and "attachments" not in str(history)
    buyer, _ = authorize(setup["users"][Role.ACHIZITII])
    assert "Pret-confidential-98765.pdf" in str(buyer.get(f'/api/purchase-orders/{order["id"]}/history').json)
    assert client.get(f'/api/attachments/{result["attachment"]["id"]}/download').status_code == 403


def test_draft_receipt_files_follow_parent_visibility(setup, session, storage):
    order = parent(setup, session, "orders")
    receipt = create_receipt(actor_user_id=setup["users"][Role.DEPOZIT], purchase_order_id=order["id"], delivery_reference="AV-2",
        received_at="2026-10-20T09:00:00Z", items=[{"purchase_order_item_id": order["items"][0]["id"], "received_quantity": "1"}])
    result = upload(setup, receipt, kind="receipts", role=Role.DEPOZIT).json
    for role in (Role.ACHIZITII, Role.CONTABILITATE):
        client, _ = authorize(setup["users"][role])
        assert client.get(endpoint("receipts", receipt["id"])).status_code == 404
        assert client.get(f'/api/attachments/{result["attachment"]["id"]}/download').status_code == 404


def test_stale_versions_csrf_and_upload_quota(setup, session, storage, monkeypatch):
    result = upload(setup, setup["invoice"]).json
    assert upload(setup, setup["invoice"]).status_code == 409
    client, _ = authorize(setup["users"][Role.CONTABILITATE])
    assert client.post(endpoint("invoices", setup["invoice"]["id"]), data={}).status_code == 401
    monkeypatch.setattr("app.services.attachments.MAX_ATTACHMENTS", 1)
    assert upload(setup, result["document"]).status_code == 409
    assert session.scalar(select(func.count()).select_from(Attachment)) == 1


def test_files_survive_a_new_application_instance(setup, session, storage, monkeypatch):
    result = upload(setup, setup["invoice"]).json
    app = create_app()
    app.config.update(ATTACHMENT_STORAGE_PATH=str(storage), JWT_COOKIE_SECURE=False)
    monkeypatch.setattr(session, "remove", lambda: None, raising=False)
    with app.app_context():
        client, _ = authorize(setup["users"][Role.CONTABILITATE])
        response = client.get(f'/api/attachments/{result["attachment"]["id"]}/download')
        assert response.status_code == 200
        assert response.data == PDF


def test_check_command_reports_unreferenced_files_without_deleting_them(setup, session, storage):
    upload(setup, setup["invoice"])
    orphan = storage / "objects" / ("f" * 64)
    orphan.write_bytes(PDF)
    result = current_app.test_cli_runner().invoke(args=["check-attachments"])
    assert result.exit_code == 1
    assert "neasociate: 1" in result.output
    assert orphan.read_bytes() == PDF
    assert check_attachment_storage()["referenced"] == 1


def test_active_attachment_identity_is_immutable_in_postgresql(setup, session, storage):
    result = upload(setup, setup["invoice"]).json
    for statement in ("UPDATE attachments SET original_name = 'replacement.pdf' WHERE id = :id",
            "UPDATE attachments SET invoice_id = NULL, receipt_id = :receipt_id WHERE id = :id",
            "UPDATE attachments SET content_sha256 = repeat('a', 64) WHERE id = :id"):
        with pytest.raises(DBAPIError), session.begin_nested():
            session.execute(text(statement), {"id": result["attachment"]["id"], "receipt_id": setup["receipt"]["id"]})


def test_malformed_uploads_and_pagination_do_not_change_the_document(setup, session, storage):
    from werkzeug.datastructures import MultiDict
    client, headers = authorize(setup["users"][Role.CONTABILITATE])
    target = endpoint("invoices", setup["invoice"]["id"])
    assert client.post(target, headers=headers, json={}).status_code == 415
    for changes in ({"version": "True"}, {"version": "2147483647"}, {"upload_key": "bad-key"}, {"reason": " "}):
        data = {"file": (BytesIO(PDF), "factura.pdf"), "version": "1", "upload_key": str(uuid4()), "reason": "Document"}
        assert client.post(target, headers=headers, data={**data, **changes}).status_code == 400
    duplicate = MultiDict([("file", (BytesIO(PDF), "first.pdf")), ("file", (BytesIO(PDF), "second.pdf")),
        ("version", "1"), ("upload_key", str(uuid4())), ("reason", "Document")])
    assert client.post(target, headers=headers, data=duplicate).status_code == 400
    assert client.get(target + "?page=0").status_code == 400
    assert client.get(target + "?per_page=1000").status_code == 400
    assert client.get(target + "?page=1&page=2").status_code == 400
    assert client.get(target + "?private=true").status_code == 400
    assert session.scalar(select(func.count()).select_from(Attachment)) == 0
    assert get_invoice(setup["invoice"]["id"])["version"] == 1


@pytest.mark.parametrize("name", ["../secret.pdf", "C:\\secret.pdf", "invoice\x00.pdf", "invoice\n.pdf", "a" * 201 + ".pdf", ".pdf", "invoice.svg"])
def test_unsafe_names_are_rejected(name):
    with pytest.raises(ValueError):
        file_name(name)
