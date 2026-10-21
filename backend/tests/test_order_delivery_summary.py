import pytest

from app.models import Role, User
from app.services.purchase_orders import confirm_order, create_order
from test_receipts import authorize, confirm_payload, payload, setup


@pytest.mark.parametrize("role", [Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE])
def test_delivery_summary_tracks_confirmed_receipts(session, setup, role):
    reader = User(name="Cititor", email="summary-reader@example.com", role=role,
                  password_hash="unused", token_version=1, is_active=True)
    session.add(reader)
    session.flush()
    reader_id = reader.id
    session.commit()
    client, _ = authorize(reader_id)
    warehouse, headers = authorize(setup["warehouse"])
    order_id = setup["order"]["id"]

    def check(expected, remainder):
        response = client.get("/api/purchase-orders?per_page=1")
        assert response.status_code == 200
        order = response.json["orders"][0]
        assert order["delivery_status"] == expected
        assert order["status"] == "CONFIRMED"
        delivery = client.get(f"/api/purchase-orders/{order_id}/delivery").json["delivery"]
        assert delivery["delivery_status"] == expected
        assert delivery["items"][0]["remaining_quantity"] == remainder
        if role == Role.DEPOZIT:
            assert "currency" not in order
            assert "unit_price" not in delivery["items"][0]

    check("NOT_RECEIVED", "10.000")
    for quantity, expected, remainder in [("7.700", "PARTIAL", "2.300"), ("2.300", "COMPLETE", "0.000")]:
        previous = client.get("/api/purchase-orders").json["orders"][0]["delivery_status"]
        receipt = warehouse.post("/api/receipts", headers=headers, json=payload(setup, items=[{
            "purchase_order_item_id": setup["order"]["items"][0]["id"], "received_quantity": quantity,
        }])).json["receipt"]
        assert client.get("/api/purchase-orders").json["orders"][0]["delivery_status"] == previous
        assert warehouse.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers,
                              json=confirm_payload(receipt, quantity, "0", "0")).status_code == 200
        check(expected, remainder)


def test_delivery_summary_requires_all_lines_and_keeps_pagination(session, setup):
    order = create_order(actor_user_id=setup["buyer"], supplier_id=setup["supplier"], currency="RON", items=[{
        "product_id": setup["product"], "quantity": quantity, "unit_price": "1", "vat_rate": "0", "expected_date": "2026-11-10",
    } for quantity in ("5.250", "4.750")])
    order = confirm_order(actor_user_id=setup["buyer"], order_id=order["id"], version=1)
    client, headers = authorize(setup["warehouse"])
    for index, expected in [(0, "PARTIAL"), (1, "COMPLETE")]:
        line = order["items"][index]
        receipt = client.post("/api/receipts", headers=headers, json=payload(setup, purchase_order_id=order["id"], items=[{
            "purchase_order_item_id": line["id"], "received_quantity": line["quantity"],
        }])).json["receipt"]
        assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers,
                           json=confirm_payload(receipt, line["quantity"], "0", "0")).status_code == 200
        pages = [client.get(f"/api/purchase-orders?page={number}&per_page=1").json for number in (1, 2)]
        page = next(page for page in pages if page["orders"][0]["id"] == order["id"])
        assert len({page["orders"][0]["id"] for page in pages}) == 2
        assert page["total"] == 2
        assert len(page["orders"]) == 1
        assert page["orders"][0]["id"] == order["id"]
        assert page["orders"][0]["delivery_status"] == expected
        other = next(page["orders"][0] for page in pages if page["orders"][0]["id"] != order["id"])
        assert other["delivery_status"] == "NOT_RECEIVED"
    assert client.get("/api/purchase-orders?page=3&per_page=1").json["orders"] == []


def test_delivery_summary_ignores_rejected_and_pending_goods(session, setup):
    client, headers = authorize(setup["warehouse"])
    receipt = client.post("/api/receipts", headers=headers, json=payload(setup)).json["receipt"]
    assert client.post(f"/api/receipts/{receipt['id']}/confirm", headers=headers,
                       json=confirm_payload(receipt, "0", "1", "2.125")).status_code == 200
    assert client.get("/api/purchase-orders").json["orders"][0]["delivery_status"] == "NOT_RECEIVED"


def test_delivery_summary_is_not_applicable_to_drafts(session, setup):
    order = create_order(actor_user_id=setup["buyer"], supplier_id=setup["supplier"], currency="RON", items=[])
    client, _ = authorize(setup["buyer"])
    first = client.get("/api/purchase-orders?page=1&per_page=1").json["orders"][0]
    assert first["id"] == order["id"]
    assert first["delivery_status"] is None
    assert client.get(f"/api/purchase-orders/{order['id']}/delivery").json["delivery"]["delivery_status"] is None


@pytest.mark.parametrize("role", [Role.ACHIZITII, Role.DEPOZIT, Role.CONTABILITATE])
def test_order_list_displays_supplier_and_lines_without_leaking_prices(session, setup, role):
    reader = User(name="Cititor", email="order-table-reader@example.com", role=role,
                  password_hash="unused", token_version=1, is_active=True)
    session.add(reader)
    session.flush()
    client, _ = authorize(reader.id)
    session.commit()
    response = client.get("/api/purchase-orders")
    assert response.status_code == 200
    order = response.json["orders"][0]
    assert order["supplier_name"] == "Furnizor"
    item = order["items"][0]
    assert item["id"] == setup["order"]["items"][0]["id"]
    assert item["sku"] == "P1"
    assert item["description"] == "Produs comandat"
    assert item["quantity"] == "10.000"
    assert item["unit"] == "KG"
    if role == Role.DEPOZIT:
        assert "unit_price" not in item
        assert "currency" not in order
    else:
        assert item["unit_price"] == "2.0000"
        assert order["currency"] == "RON"


def test_order_list_groups_all_lines_only_for_current_page_and_keeps_snapshots(session, setup):
    from app.models import Product, Supplier

    supplier = session.get(Supplier, setup["supplier"])
    supplier.name = "Furnizor redenumit"
    product = session.get(Product, setup["product"])
    product.name = "Nume nou in catalog"
    session.commit()
    second = create_order(actor_user_id=setup["buyer"], supplier_id=setup["supplier"], currency="EUR", items=[{
        "product_id": setup["product"], "quantity": amount, "unit_price": price, "vat_rate": "0", "expected_date": "2026-11-10",
    } for amount, price in [("1.125", "3.1234"), ("2.500", "4.5000")]])
    client, _ = authorize(setup["buyer"])
    first = client.get("/api/purchase-orders?page=2&per_page=1").json
    assert first["total"] == 2
    assert first["orders"][0]["supplier_name"] == "Furnizor redenumit"
    assert first["orders"][0]["items"][0]["description"] == "Produs comandat"
    following = client.get("/api/purchase-orders?page=1&per_page=1").json["orders"]
    assert len(following) == 1
    assert following[0]["id"] == second["id"]
    assert [item["line_number"] for item in following[0]["items"]] == [1, 2]
    assert [item["unit_price"] for item in following[0]["items"]] == ["3.1234", "4.5000"]
    assert all(item["description"] == "Nume nou in catalog" for item in following[0]["items"])
