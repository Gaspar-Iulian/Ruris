import json
from unittest.mock import patch

from flask import current_app
from flask_jwt_extended import create_access_token, get_csrf_token
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models import AuditEvent, Product, Role, User
from app.services.products import ProductCreationForbiddenError, create_product


@pytest.fixture
def client(session):
    current_app.config["JWT_COOKIE_SECURE"] = False
    return current_app.test_client()


def authorize(client, session, role):
    user = User(name="Test", email=f"product-{role.value}@example.com", role=role,
                password_hash="unused", token_version=1, is_active=True)
    session.add(user)
    session.flush()
    user_id = user.id
    session.commit()
    token = create_access_token(identity=str(user_id), additional_claims={"token_version": 1})
    client.set_cookie("access_token_cookie", token, path="/api")
    return {"X-CSRF-TOKEN": get_csrf_token(token)}, user_id


def payload(**changes):
    return {"sku": " filtru-01 ", "name": " Filtru ulei ", "unit": " buc ", **changes}


def test_create_product_normalizes_and_audits(client, session):
    headers, actor = authorize(client, session, Role.ACHIZITII)
    response = client.post("/api/products", headers=headers, json=payload())
    assert response.status_code == 201
    product = response.json["product"]
    assert product == {"id": product["id"], "sku": "FILTRU-01", "name": "Filtru ulei", "unit": "BUC", "is_active": True}
    event = session.scalar(select(AuditEvent))
    assert event.entity_type == "products"
    assert event.entity_id == product["id"]
    assert event.actor_user_id == actor
    assert event.action == "CREATE"
    assert event.before_data is None
    assert event.after_data == {key: value for key, value in product.items() if key != "id"}
    assert "Set-Cookie" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("role", list(Role))
def test_product_role_permissions(client, session, role):
    session.add(Product(sku="P1", name="Produs", unit="KG"))
    session.commit()
    headers, _ = authorize(client, session, role)
    response = client.get("/api/products")
    assert response.status_code == (403 if role == Role.ADMIN else 200)
    if role != Role.ADMIN:
        assert set(response.json["products"][0]) == {"id", "sku", "name", "unit", "is_active"}
        assert response.json["products"][0]["sku"] == "P1"
    assert client.post("/api/products", headers=headers, json=payload()).status_code == (
        201 if role == Role.ACHIZITII else 403
    )


def test_duplicate_sku_rolls_back_without_extra_audit(client, session):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.post("/api/products", headers=headers, json=payload()).status_code == 201
    assert client.post("/api/products", headers=headers, json=payload(sku="FILTRU-01")).status_code == 409
    assert session.scalar(select(func.count()).select_from(Product)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
    assert client.post("/api/products", headers=headers, json=payload(sku="FILTRU-02")).status_code == 201


@pytest.mark.parametrize("changes", [
    {"sku": " "}, {"sku": "x" * 65}, {"sku": "P 1"}, {"sku": "-P1"}, {"sku": None},
    {"sku": "P/1"}, {"sku": "P\n1"}, {"sku": 123}, {"sku": "șurub"},
    {"name": " "}, {"name": "x" * 201}, {"name": False},
    {"unit": "cutie"}, {"unit": None}, {"unit": 1},
    {"is_active": False}, {"stock": 5}, {"actor_user_id": 7},
])
def test_invalid_product_leaves_no_data(client, session, changes):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.post("/api/products", headers=headers, json=payload(**changes)).status_code == 400
    assert session.scalar(select(func.count()).select_from(Product)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_auth_csrf_body_and_pagination(client, session):
    assert client.get("/api/products").status_code == 401
    assert client.post("/api/products", json=payload()).status_code == 401
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.post("/api/products", json=payload()).status_code == 401
    assert client.post("/api/products", headers=headers, data="x").status_code == 415
    assert client.post("/api/products", headers=headers, data="{", content_type="application/json").status_code == 400
    for data in ([], None, {"sku": "P1"}):
        assert client.post("/api/products", headers=headers, data=json.dumps(data), content_type="application/json").status_code == 400
    assert client.post("/api/products", headers=headers, json=payload(name="x" * 5000)).status_code == 413
    for sku in ("P1", "P2"):
        assert client.post("/api/products", headers=headers, json=payload(sku=sku)).status_code == 201
    response = client.get("/api/products?page=2&per_page=1")
    assert response.json["total"] == 2
    assert response.json["products"][0]["sku"] == "P2"
    assert client.get("/api/products?page=3&per_page=1").json["products"] == []
    for query in ("page=0", "page=1000001", "per_page=101", "page=x", "page=1&page=2", "role=ADMIN"):
        assert client.get(f"/api/products?{query}").status_code == 400


def test_audit_failure_rolls_back_product(client, session):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    with patch("app.services.products.record_audit", side_effect=SQLAlchemyError("test")):
        response = client.post("/api/products", headers=headers, json=payload())
        assert response.status_code == 503
        assert "test" not in response.get_data(as_text=True)
    assert session.scalar(select(func.count()).select_from(Product)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("inactive", [False, True])
def test_service_rechecks_actor(client, session, inactive):
    _, actor = authorize(client, session, Role.ACHIZITII if inactive else Role.DEPOZIT)
    if inactive:
        session.get(User, actor).is_active = False
        session.commit()
    with pytest.raises(ProductCreationForbiddenError):
        create_product(actor_user_id=actor, **payload())
    assert session.scalar(select(func.count()).select_from(Product)) == 0


@pytest.mark.parametrize("sku,unit", [("lowercase", "BUC"), ("P1", "XXX")])
def test_database_rejects_invalid_values_without_orm_validation(session, sku, unit):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.execute(text("INSERT INTO products (sku, name, unit) VALUES (:sku, 'Test', :unit)"),
                            {"sku": sku, "unit": unit})
    assert session.scalar(select(func.count()).select_from(Product)) == 0


def test_all_base_units_can_be_stored(session):
    for unit in ("BUC", "KG", "L", "M", "M2", "M3"):
        session.add(Product(sku=f"P-{unit}", name="Produs test", unit=unit))
    session.flush()
    assert session.scalar(select(func.count()).select_from(Product)) == 6


@pytest.fixture
def product_id(session):
    product = Product(sku="P1", name="Produs initial", unit="BUC")
    session.add(product)
    session.flush()
    value = product.id
    session.commit()
    return value


def test_update_name_audits_and_preserves_identity(client, session, product_id):
    headers, actor = authorize(client, session, Role.ACHIZITII)
    response = client.patch(f"/api/products/{product_id}", headers=headers,
                            json={"name": " Nume nou ", "reason": " Corectie denumire "})
    assert response.status_code == 200
    assert response.json["product"] == {"id": product_id, "sku": "P1", "name": "Nume nou", "unit": "BUC", "is_active": True}
    event = session.scalar(select(AuditEvent))
    assert event.action == "UPDATE"
    assert event.entity_type == "products"
    assert event.entity_id == product_id
    assert event.actor_user_id == actor
    assert event.reason == "Corectie denumire"
    assert event.before_data["name"] == "Produs initial"
    assert event.after_data["name"] == "Nume nou"
    assert response.headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in response.headers


def test_deactivation_reactivation_and_noops(client, session, product_id):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    for active in (False, False, True, True):
        response = client.patch(f"/api/products/{product_id}/status", headers=headers,
                                json={"is_active": active, "reason": "Decizie achizitii"})
        assert response.status_code == 200
        assert response.json["product"]["is_active"] is active
        listing = client.get("/api/products").json
        assert listing["total"] == 1
        assert listing["products"][0]["is_active"] is active
    assert client.patch(f"/api/products/{product_id}", headers=headers,
                        json={"name": " Produs initial ", "reason": "Verificare"}).status_code == 200
    events = session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    assert [event.action for event in events] == ["DEACTIVATE", "ACTIVATE"]
    assert events[0].before_data["is_active"] is True
    assert events[0].after_data["is_active"] is False


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DEPOZIT, Role.CONTABILITATE])
def test_other_roles_cannot_change_products(client, session, product_id, role):
    headers, _ = authorize(client, session, role)
    assert client.patch(f"/api/products/{product_id}", headers=headers,
                        json={"name": "Alt nume", "reason": "Test"}).status_code == 403
    assert client.patch(f"/api/products/{product_id}/status", headers=headers,
                        json={"is_active": False, "reason": "Test"}).status_code == 403
    assert session.get(Product, product_id).is_active is True
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("suffix,data", [
    ("", {"name": "Nou"}), ("", {"name": "Nou", "reason": " "}),
    ("", {"name": "Nou", "reason": False}), ("", {"name": "Nou", "reason": "x" * 1001}),
    ("", {"name": " ", "reason": "Test"}), ("", {"name": 2, "reason": "Test"}),
    ("", {"sku": "P2", "reason": "Test"}), ("", {"unit": "KG", "reason": "Test"}),
    ("", {"is_active": False, "reason": "Test"}),
    ("/status", {"is_active": 0, "reason": "Test"}),
    ("/status", {"is_active": "false", "reason": "Test"}),
    ("/status", {"is_active": None, "reason": "Test"}),
    ("/status", {"name": "Nou", "reason": "Test"}),
])
def test_invalid_updates_leave_product_unchanged(client, session, product_id, suffix, data):
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.patch(f"/api/products/{product_id}{suffix}", headers=headers, json=data).status_code == 400
    product = session.get(Product, product_id)
    assert product.name == "Produs initial"
    assert product.is_active is True
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("suffix,data", [
    ("", {"name": "Nou", "reason": "Test"}),
    ("/status", {"is_active": False, "reason": "Test"}),
])
def test_update_auth_not_found_and_rollback(client, session, product_id, suffix, data):
    url = f"/api/products/{product_id}{suffix}"
    assert client.patch(url, json=data).status_code == 401
    headers, _ = authorize(client, session, Role.ACHIZITII)
    assert client.patch(url, json=data).status_code == 401
    with patch("app.services.products.record_audit", side_effect=SQLAlchemyError("test")):
        assert client.patch(url, headers=headers, json=data).status_code == 503
    product = session.get(Product, product_id)
    assert product.name == "Produs initial"
    assert product.is_active is True
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    for missing in (888, 9223372036854775808):
        assert client.patch(f"/api/products/{missing}{suffix}", headers=headers, json=data).status_code == 404


@pytest.mark.parametrize("inactive", [False, True])
def test_update_service_rechecks_actor(client, session, product_id, inactive):
    from app.services.products import ProductManagementForbiddenError, change_product

    _, actor = authorize(client, session, Role.ACHIZITII if inactive else Role.DEPOZIT)
    if inactive:
        session.get(User, actor).is_active = False
        session.commit()
    with pytest.raises(ProductManagementForbiddenError):
        change_product(actor_user_id=actor, product_id=product_id, reason="Test", changes={"is_active": False})
    assert session.get(Product, product_id).is_active is True
