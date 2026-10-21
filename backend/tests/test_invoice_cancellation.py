from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models import AuditEvent, Invoice, InvoiceAllocation, InvoiceIssue, InvoiceItem, PurchaseOrderItem, Role, StockMovement
from app.services.audit import record_audit
from app.services.exchange_rates import ExchangeRateUnavailable
from app.services.notifications import build_blocked_invoice_digests
from test_invoice_allocations import authorize, payload, setup, url
from test_invoice_approval import approve, prepare
from test_invoice_verification import cover, verify


def cancel(setup, version=1, **changes):
    return setup["client"].post(f'/api/invoices/{setup["invoice"]["id"]}/cancel', headers=setup["headers"],
        json={"version": version, "reason": " Factura duplicata ", **changes})


def prepare_cancellation(setup, session, state):
    item = session.get(InvoiceItem, setup["invoice"]["items"][0]["id"])
    source_id = setup["receipt"]["items"][0]["purchase_order_item_id"]
    item.purchase_order_item_id = source_id
    session.commit()
    if state == "VERIFIED":
        cover(setup, session)
        assert verify(setup, 2).json["invoice"]["status"] == "VERIFIED"
        return 3
    assert setup["client"].post(url(setup), headers=setup["headers"], json=payload(setup)).status_code == 201
    if state == "BLOCKED":
        with patch("app.services.invoice_verification.get_eur_rate", side_effect=ExchangeRateUnavailable("test")):
            assert verify(setup, 2).json["invoice"]["status"] == "BLOCKED"
        return 3
    return 2


@pytest.mark.parametrize("state", ["DRAFT", "BLOCKED", "VERIFIED"])
def test_cancellation_releases_goods_closes_issues_retains_document_and_stock(session, setup, state):
    version = prepare_cancellation(setup, session, state)
    stock = session.scalar(select(func.sum(StockMovement.quantity_delta)))
    response = cancel(setup, version)
    assert response.status_code == 200, response.json
    invoice = response.json["invoice"]
    assert (invoice["status"], invoice["version"]) == ("CANCELLED", version + 1)
    assert invoice["cancelled_by_id"] == setup["users"][Role.CONTABILITATE]
    assert invoice["cancelled_at"] is not None
    assert invoice["cancellation_reason"] == "Factura duplicata"
    assert invoice["total_ron"] is None
    assert session.scalar(select(func.sum(StockMovement.quantity_delta))) == stock
    assert session.scalar(select(func.count()).select_from(InvoiceAllocation).where(InvoiceAllocation.status == "ACTIVE")) == 0
    assert session.scalar(select(func.count()).select_from(InvoiceAllocation).where(InvoiceAllocation.status == "RELEASED")) == 1
    assert session.scalar(select(func.count()).select_from(InvoiceIssue).where(InvoiceIssue.resolved_at.is_(None))) == 0
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "CANCEL"))
    assert event.reason == invoice["cancellation_reason"]
    assert event.before_data["status"] == state
    assert event.after_data["status"] == "CANCELLED"
    context_url = f"/api/purchase-orders/{session.get(PurchaseOrderItem, invoice['items'][0]['purchase_order_item_id']).purchase_order_id}/invoicing"
    context = setup["client"].get(context_url).json["order"]
    assert context["items"][0]["registered_quantity"] == "0.000"
    assert context["items"][0]["remaining_to_invoice"] == "10.000"
    assert context["items"][0]["available_quantity"] == "6.000"
    assert context["invoice_documents"][0]["status"] == "CANCELLED"
    matching = setup["client"].get(f'/api/invoices/{invoice["id"]}/matching').json
    assert matching["invoice"] == invoice
    assert matching["allocations"] == matching["issues"] == []
    assert build_blocked_invoice_digests()["messages"] == []
    assert response.headers["Cache-Control"] == "no-store"


def test_cancelled_invoice_is_read_only_and_cannot_be_reactivated(session, setup):
    assert cancel(setup).status_code == 200
    invoice_url = f'/api/invoices/{setup["invoice"]["id"]}'
    assert cancel(setup, 2).status_code == 409
    assert verify(setup, 2).status_code == 409
    assert approve(setup, version=2).status_code == 409
    assert setup["client"].patch(invoice_url, headers=setup["headers"], json={**setup["data"], "version": 2, "reason": "Edit"}).status_code == 409
    assert setup["client"].patch(invoice_url + "/declared-totals", headers=setup["headers"],
        json={"version": 2, "reason": "Edit", "declared_totals": setup["data"]["declared_totals"]}).status_code == 409
    assert setup["client"].post(url(setup), headers=setup["headers"], json=payload(setup, version=2)).status_code == 409
    assert setup["client"].post(invoice_url + "/pay", headers=setup["headers"], json={"version": 2, "reason": "Plata",
        "paid_at": datetime.now(timezone.utc).isoformat(), "payment_reference": "OP-1"}).status_code == 409
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "CANCEL")) == 1


@pytest.mark.parametrize("paid", [False, True])
def test_approved_and_paid_invoices_cannot_be_cancelled(session, setup, paid):
    prepare(setup, session)
    assert approve(setup).status_code == 200
    version = 4
    if paid:
        response = setup["client"].post(f'/api/invoices/{setup["invoice"]["id"]}/pay', headers=setup["headers"], json={
            "version": 4, "reason": "Plata", "paid_at": datetime.now(timezone.utc).isoformat(), "payment_reference": "OP-1"})
        assert response.status_code == 200
        version = 5
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    assert cancel(setup, version).status_code == 409
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
    assert session.scalar(select(InvoiceAllocation.status)) == "ACTIVE"


@pytest.mark.parametrize("changes", [{"reason": " "}, {"reason": None}, {"reason": "x" * 1001}, {"version": True}, {"version": 0}, {"version": "1"}, {"version": 2147483647}])
def test_invalid_cancellation_does_not_change_document(session, setup, changes):
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    assert cancel(setup, **changes).status_code == 400
    assert session.get(Invoice, setup["invoice"]["id"]).status == "DRAFT"
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before


@pytest.mark.parametrize("role", list(Role))
def test_cancellation_permissions_and_missing_document(session, setup, role):
    client, headers = authorize(setup["users"][role])
    response = client.post('/api/invoices/999999/cancel', headers=headers, json={"version": 1, "reason": "Control"})
    assert response.status_code == (404 if role == Role.CONTABILITATE else 403)


def test_late_audit_failure_rolls_back_cancellation_and_releases(session, setup):
    version = prepare_cancellation(setup, session, "BLOCKED")
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    open_issues = session.scalar(select(func.count()).select_from(InvoiceIssue).where(InvoiceIssue.resolved_at.is_(None)))

    def fail_cancel(**kwargs):
        if kwargs["action"] == "CANCEL":
            raise SQLAlchemyError("test")
        return record_audit(**kwargs)

    with patch("app.services.invoice_cancellation.record_audit", side_effect=fail_cancel):
        assert cancel(setup, version).status_code == 503
    assert session.get(Invoice, setup["invoice"]["id"]).status == "BLOCKED"
    assert session.scalar(select(InvoiceAllocation.status)) == "ACTIVE"
    assert session.scalar(select(func.count()).select_from(InvoiceIssue).where(InvoiceIssue.resolved_at.is_(None))) == open_issues
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_database_requires_cancellation_metadata(session, setup):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.get(Invoice, setup["invoice"]["id"]).status = "CANCELLED"
            session.flush()


def test_replacement_invoice_can_use_released_goods_without_changing_stock(session, setup):
    version = prepare_cancellation(setup, session, "VERIFIED")
    assert cancel(setup, version).status_code == 200
    data = {**setup["data"], "number": "REPLACEMENT", "currency": "RON",
        "declared_totals": {"net_amount": "12", "vat_amount": "2.28", "total_amount": "14.28"},
        "items": [{**setup["data"]["items"][0], "quantity": "6",
                   "purchase_order_item_id": setup["receipt"]["items"][0]["purchase_order_item_id"]}]}
    second = setup["client"].post('/api/invoices', headers=setup["headers"], json=data).json["invoice"]
    assert setup["client"].post(f'/api/invoices/{second["id"]}/allocations', headers=setup["headers"],
        json=payload(setup, invoice=second, quantity="6")).status_code == 201
    assert setup["client"].post(f'/api/invoices/{second["id"]}/verify', headers=setup["headers"], json={"version": 2}).json["invoice"]["status"] == "VERIFIED"
    assert session.scalar(select(func.sum(StockMovement.quantity_delta))) == 6


def test_cancellation_removes_current_blockers_but_keeps_sent_notification_history(session, setup):
    from app.services.email_delivery import send_blocked_invoice_digests_local

    version = prepare_cancellation(setup, session, "BLOCKED")
    with patch("app.services.email_delivery.send_to_local_mailpit"):
        assert send_blocked_invoice_digests_local()["sent"] == 1
    journal = setup["client"].get('/api/notifications').json
    assert journal["total"] == 1
    assert cancel(setup, version).status_code == 200
    assert build_blocked_invoice_digests()["messages"] == []
    assert setup["client"].get('/api/notifications').json == journal


def test_approval_and_cancellation_cannot_both_succeed(session, monkeypatch):
    import importlib.util
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from threading import Barrier
    from uuid import uuid4

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from flask import current_app
    from sqlalchemy import event, text
    from sqlalchemy.orm import scoped_session, sessionmaker
    from sqlalchemy.schema import CreateSchema, DropSchema

    from app.extensions import db
    from app.models import User
    from app.services.invoice_cancellation import cancel_invoice
    from app.services.invoice_verification import approve_invoice
    from app.services.invoices import InvoiceConflictError
    from test_invoice_allocations import seed_data

    app, engine = current_app._get_current_object(), db.engine
    schema = f"ruris_cancel_test_{uuid4().hex}"
    scoped = scoped_session(sessionmaker(bind=engine))
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})
            with Operations.context(MigrationContext.configure(connection)):
                for path in sorted((Path(__file__).resolve().parents[1] / "migrations" / "versions").glob("0*.py")):
                    spec = importlib.util.spec_from_file_location(f"cancel_{path.stem}", path)
                    migration = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(migration)
                    migration.upgrade()

        def use_schema(session, transaction, connection):
            connection.execute(text("SELECT set_config('search_path', :schema, true)"), {"schema": schema})

        event.listen(scoped.session_factory, "after_begin", use_schema)
        with monkeypatch.context() as patcher:
            patcher.setattr(db, "session", scoped)
            data = seed_data(scoped)
            prepare(data, scoped)
            other = User(name="Contabil 2", email="cancel-other@example.com", role=Role.CONTABILITATE,
                         password_hash="unused", token_version=1, is_active=True)
            scoped.add(other)
            scoped.flush()
            other_id, invoice_id, actor_id = other.id, data["invoice"]["id"], data["users"][Role.CONTABILITATE]
            scoped.commit()
            barrier = Barrier(2)

            def worker(action, actor):
                with app.app_context():
                    try:
                        scoped.execute(text("SET LOCAL lock_timeout = '5s'"))
                        barrier.wait(timeout=10)
                        if action == "cancel":
                            cancel_invoice(actor_user_id=actor, invoice_id=invoice_id, version=3, reason="Duplicat")
                        else:
                            assert approve_invoice(actor_user_id=actor, invoice_id=invoice_id, version=3, reason="Control")["approved"]
                        return action
                    except InvoiceConflictError:
                        return "conflict"
                    finally:
                        scoped.remove()

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(worker, "cancel", actor_id), executor.submit(worker, "approve", other_id)]
                results = [future.result(timeout=15) for future in futures]
            assert results.count("conflict") == 1
            invoice = scoped.get(Invoice, invoice_id)
            allocation = scoped.scalar(select(InvoiceAllocation))
            assert (invoice.status, allocation.status) in {("CANCELLED", "RELEASED"), ("APPROVED", "ACTIVE")}
            assert scoped.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action.in_(("CANCEL", "APPROVE")))) == 1
    finally:
        scoped.remove()
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
