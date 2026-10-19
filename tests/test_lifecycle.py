from tests.conftest import order_body


def make_order(client, qty=3):
    r = client.post("/orders", json=order_body([{"sku": "WMT-1001", "quantity": qty, "unit_price": 2}]))
    return r.json()["id"]


def move(client, oid, status):
    return client.patch(f"/orders/{oid}/status", json={"status": status})


def test_full_lifecycle_deducts_stock_on_ship(stocked):
    oid = make_order(stocked, qty=3)
    for status in ("PICKING", "PACKED", "SHIPPED", "DELIVERED"):
        assert move(stocked, oid, status).status_code == 200
    item = stocked.get("/inventory/WMT-1001").json()
    assert item["on_hand"] == 7
    assert item["reserved"] == 0


def test_cancel_releases_reservation(stocked):
    oid = make_order(stocked, qty=4)
    assert move(stocked, oid, "CANCELLED").status_code == 200
    item = stocked.get("/inventory/WMT-1001").json()
    assert item["reserved"] == 0
    assert item["on_hand"] == 10


def test_invalid_transitions_rejected(stocked):
    oid = make_order(stocked)
    assert move(stocked, oid, "SHIPPED").status_code == 409
    move(stocked, oid, "CANCELLED")
    assert move(stocked, oid, "PICKING").status_code == 409


def test_cannot_cancel_after_shipping(stocked):
    oid = make_order(stocked)
    for status in ("PICKING", "PACKED", "SHIPPED"):
        move(stocked, oid, status)
    assert move(stocked, oid, "CANCELLED").status_code == 409


def test_status_update_unknown_order(stocked):
    assert move(stocked, 9999, "PICKING").status_code == 404
