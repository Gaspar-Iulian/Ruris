from unittest.mock import patch

from flask import current_app
from flask_jwt_extended import create_access_token, get_csrf_token
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models import AuditEvent, Role, Supplier, User
from app.services.suppliers import SupplierCreationForbiddenError, create_supplier


@pytest.fixture
def client(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    return current_app.test_client()


def authorize(client, session, role):
    user = User(name="Test", email=f"supplier-{role.value}@example.com", role=role,
                password_hash="unused", token_version=1, is_active=True)
    session.add(user)
    session.flush()
    user_id = user.id
    session.commit()
    token = create_access_token(identity=str(user_id), additional_claims={"token_version": 1})
    client.set_cookie("access_token_cookie", token, path="/api")
    return {"X-CSRF-TOKEN": get_csrf_token(token)}, user_id


def payload(**changes):
    return {"name": " Furnizor test ", "tax_country": " ro ", "tax_id": "ro 12345", **changes}


def test_creation_normalization_and_audit_are_atomic(client, session):
    headers, actor = authorize(client, session, Role.ACHIZITII)
    response = client.post("/api/suppliers", headers=headers, json=payload())
    assert response.status_code == 201
    supplier = response.json["supplier"]
    assert supplier == {"id": supplier["id"], "name": "Furnizor test", "tax_country": "RO",
                        "tax_id": "12345", "email": None, "is_active": True}
    event = session.scalar(select(AuditEvent).where(AuditEvent.entity_type == "suppliers"))
    assert event.actor_user_id == actor
    assert event.entity_id == supplier["id"]
    assert event.action == "CREATE"
    assert event.after_data == {key: value for key, value in supplier.items() if key != "id"}
    assert response.headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in response.headers


@pytest.mark.parametrize("role", list(Role))
def test_role_permissions_and_warehouse_projection(client, session, role):
    session.add(Supplier(name="Firma", tax_country="RO", tax_id="123", email="firma@example.com"))
    session.commit()
    headers, _ = authorize(client, session, role)
    response = client.get("/api/suppliers")
    assert response.status_code == (403 if role == Role.ADMIN else 200)
    if role != Role.ADMIN:
        fields = set(response.json["suppliers"][0])
        assert fields == ({"id", "name", "is_active"} if role == Role.DEPOZIT else
                          {"id", "name", "is_active", "tax_country", "tax_id", "email"})
    assert client.post("/api/suppliers", headers=headers, json=payload()).status_code == (
        201 if role == Role.ACHIZITII else 403
    )


def test_duplicate_identity_and_country_scope(client, session):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.post("/api/suppliers", headers=headers, json=payload()).status_code == 201
    assert client.post("/api/suppliers", headers=headers, json=payload(tax_id="12345")).status_code == 409
    assert client.post("/api/suppliers", headers=headers, json=payload(tax_country="DE", tax_id="12345")).status_code == 201
    assert session.scalar(select(func.count()).select_from(Supplier)) == 2
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"name": 3}, {"tax_country": "Romania"}, {"tax_country": None},
    {"tax_id": "RO"}, {"tax_id": "RO-123"}, {"tax_id": "RORO123"}, {"tax_id": 123},
    {"email": "invalid"}, {"email": False}, {"is_active": False}, {"actor_user_id": 9},
])
def test_invalid_input_does_not_create_supplier_or_audit(client, session, changes):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.post("/api/suppliers", headers=headers, json=payload(**changes)).status_code == 400
    assert session.scalar(select(func.count()).select_from(Supplier)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_auth_csrf_pagination_and_optional_email(client, session):
    assert client.get("/api/suppliers").status_code == 401
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.post("/api/suppliers", json=payload()).status_code == 401
    assert client.post("/api/suppliers", headers=headers, json=payload(email=" SALES@example.com ")).json["supplier"]["email"] == "sales@example.com"
    for query in ("page=0", "per_page=101", "page=x", "page=1&page=2", "role=ADMIN"):
        assert client.get(f"/api/suppliers?{query}").status_code == 400
    response = client.get("/api/suppliers?page=2&per_page=1")
    assert response.json == {"suppliers": [], "total": 1, "page": 2, "per_page": 1}
    assert client.post("/api/suppliers", headers=headers, json=[]).status_code == 400
    assert client.post("/api/suppliers", headers=headers, data="x").status_code == 415
    assert client.post("/api/suppliers", headers=headers, json=payload(name="x" * 5000)).status_code == 413


def test_audit_failure_rolls_back_supplier(client, session):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    with patch("app.services.suppliers.record_audit", side_effect=SQLAlchemyError("test")):
        assert client.post("/api/suppliers", headers=headers, json=payload()).status_code == 503
    assert session.scalar(select(func.count()).select_from(Supplier)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_service_rechecks_actor(client, session):
    _, actor = authorize(client, session, Role.DEPOZIT)
    with pytest.raises(SupplierCreationForbiddenError):
        create_supplier(actor_user_id=actor, **payload())
    assert session.scalar(select(func.count()).select_from(Supplier)) == 0


@pytest.fixture
def supplier_id(session):
    supplier = Supplier(name="Firma initiala", tax_country="RO", tax_id="999", email="old@example.com")
    session.add(supplier)
    session.flush()
    value = supplier.id
    session.commit()
    return value


def test_update_preserves_identity_and_audits_changes(client, session, supplier_id):
    headers, actor = authorize(client, session, Role.ACHIZITII)
    response = client.patch(f"/api/suppliers/{supplier_id}", headers=headers,
                            json={"name": " Firma noua ", "email": None, "reason": " Corectie contact "})
    assert response.status_code == 200
    assert response.json["supplier"]["name"] == "Firma noua"
    assert response.json["supplier"]["email"] is None
    assert response.json["supplier"]["tax_id"] == "999"
    event = session.scalar(select(AuditEvent))
    assert event.action == "UPDATE"
    assert event.actor_user_id == actor
    assert event.entity_id == supplier_id
    assert event.before_data["name"] == "Firma initiala"
    assert event.before_data["email"] == "old@example.com"
    assert event.after_data["name"] == "Firma noua"
    assert event.after_data["email"] is None
    assert event.reason == "Corectie contact"
    assert response.headers["Cache-Control"] == "no-store"


def test_status_changes_keep_supplier_and_repeated_requests_do_not_add_audit(client, session, supplier_id):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    url = f"/api/suppliers/{supplier_id}/status"
    for active in (False, False, True, True):
        response = client.patch(url, headers=headers, json={"is_active": active, "reason": "Decizie achizitii"})
        assert response.status_code == 200
        assert response.json["supplier"]["is_active"] is active
        assert client.get("/api/suppliers").json["total"] == 1
    assert session.scalar(select(func.count()).select_from(Supplier)) == 1
    events = session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    assert [event.action for event in events] == ["DEACTIVATE", "ACTIVATE"]
    assert events[0].before_data["is_active"] is True
    assert events[0].after_data["is_active"] is False


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DEPOZIT, Role.CONTABILITATE])
def test_other_roles_cannot_change_supplier(client, session, supplier_id, role):
    headers, _ = authorize(client, session, role)
    assert client.patch(f"/api/suppliers/{supplier_id}", headers=headers,
                        json={"name": "Alt nume", "reason": "Test"}).status_code == 403
    assert client.patch(f"/api/suppliers/{supplier_id}/status", headers=headers,
                        json={"is_active": False, "reason": "Test"}).status_code == 403
    assert session.get(Supplier, supplier_id).is_active is True
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("suffix,data", [
    ("", {"name": "Firma"}), ("", {"name": "Firma", "reason": " "}),
    ("", {"name": "Firma", "reason": 1}), ("", {"reason": "Test"}),
    ("", {"tax_id": "123", "reason": "Test"}), ("", {"tax_country": "DE", "reason": "Test"}),
    ("", {"is_active": False, "reason": "Test"}), ("", {"email": "bad", "reason": "Test"}),
    ("", {"name": " ", "reason": "Test"}), ("", {"name": "X", "reason": "x" * 1001}),
    ("/status", {"is_active": 0, "reason": "Test"}),
    ("/status", {"is_active": "false", "reason": "Test"}),
    ("/status", {"is_active": None, "reason": "Test"}),
    ("/status", {"name": "Firma", "reason": "Test"}),
])
def test_invalid_changes_leave_supplier_and_audit_unchanged(client, session, supplier_id, suffix, data):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.patch(f"/api/suppliers/{supplier_id}{suffix}", headers=headers, json=data).status_code == 400
    supplier = session.get(Supplier, supplier_id)
    assert supplier.name == "Firma initiala"
    assert supplier.is_active is True
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("suffix,data", [
    ("", {"name": "Alta firma", "reason": "Test"}),
    ("/status", {"is_active": False, "reason": "Test"}),
])
def test_update_auth_and_rollback(client, session, supplier_id, suffix, data):
    url = f"/api/suppliers/{supplier_id}{suffix}"
    assert client.patch(url, json=data).status_code == 401
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.patch(url, json=data).status_code == 401
    with patch("app.services.suppliers.record_audit", side_effect=SQLAlchemyError("test")):
        assert client.patch(url, headers=headers, json=data).status_code == 503
    supplier = session.get(Supplier, supplier_id)
    assert supplier.name == "Firma initiala"
    assert supplier.is_active is True
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    assert client.patch(f"/api/suppliers/9223372036854775808{suffix}", headers=headers, json=data).status_code == 404
    assert client.patch(f"/api/suppliers/888{suffix}", headers=headers, json=data).status_code == 404


def test_normalized_noop_does_not_add_audit(client, session, supplier_id):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.patch(f"/api/suppliers/{supplier_id}", headers=headers, json={
        "name": " Firma initiala ", "email": " OLD@example.com ", "reason": "Verificare",
    }).status_code == 200
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_update_service_rechecks_actor(client, session, supplier_id):
    from app.services.suppliers import SupplierManagementForbiddenError, change_supplier

    _, actor = authorize(client, session, Role.DEPOZIT)
    with pytest.raises(SupplierManagementForbiddenError):
        change_supplier(actor_user_id=actor, supplier_id=supplier_id, reason="Test", changes={"is_active": False})
    assert session.get(Supplier, supplier_id).is_active is True
