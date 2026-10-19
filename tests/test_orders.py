from tests.conftest import order_body


def test_order_reserves_stock(stocked):
    r = stocked.post("/orders", json=order_body([{"sku": "WMT-1001", "quantity": 4, "unit_price": 2.5}]))
    assert r.status_code == 201
    assert r.json()["total"] == 10.0
    assert r.json()["status"] == "CREATED"
    item = stocked.get("/inventory/WMT-1001").json()
    assert item["reserved"] == 4
    assert item["available"] == 6


def test_insufficient_stock_rejected_and_nothing_reserved(stocked):
    r = stocked.post("/orders", json=order_body([{"sku": "WMT-1002", "quantity": 9, "unit_price": 8}]))
    assert r.status_code == 409
    assert stocked.get("/inventory/WMT-1002").json()["reserved"] == 0


def test_multi_line_order_is_all_or_nothing(stocked):
    lines = [
        {"sku": "WMT-1001", "quantity": 2, "unit_price": 5},
        {"sku": "WMT-1002", "quantity": 99, "unit_price": 8},
    ]
    assert stocked.post("/orders", json=order_body(lines)).status_code == 409
    assert stocked.get("/inventory/WMT-1001").json()["reserved"] == 0


def test_duplicate_sku_lines_are_aggregated(stocked):
    lines = [
        {"sku": "WMT-1002", "quantity": 2, "unit_price": 8},
        {"sku": "WMT-1002", "quantity": 2, "unit_price": 8},
    ]
    assert stocked.post("/orders", json=order_body(lines)).status_code == 409


def test_unknown_sku_404(stocked):
    r = stocked.post("/orders", json=order_body([{"sku": "NOPE", "quantity": 1, "unit_price": 1}]))
    assert r.status_code == 404


def test_validation_errors(stocked):
    assert stocked.post("/orders", json=order_body([])).status_code == 422
    bad_channel = order_body([{"sku": "WMT-1001", "quantity": 1, "unit_price": 1}], channel="fax")
    assert stocked.post("/orders", json=bad_channel).status_code == 422
    zero_qty = order_body([{"sku": "WMT-1001", "quantity": 0, "unit_price": 1}])
    assert stocked.post("/orders", json=zero_qty).status_code == 422


def test_get_and_list_orders(stocked):
    oid = stocked.post("/orders", json=order_body([{"sku": "WMT-1001", "quantity": 1, "unit_price": 3}])).json()["id"]
    assert stocked.get(f"/orders/{oid}").json()["id"] == oid
    assert stocked.get("/orders/9999").status_code == 404
    assert len(stocked.get("/orders?status=created").json()) == 1
    assert stocked.get("/orders?status=shipped").json() == []
