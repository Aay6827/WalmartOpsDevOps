def test_create_and_get_inventory(client):
    r = client.post("/inventory", json={"sku": "A1", "name": "Item", "on_hand": 5})
    assert r.status_code == 201
    assert r.json()["available"] == 5
    assert client.get("/inventory/A1").json()["on_hand"] == 5


def test_unknown_sku_404(client):
    assert client.get("/inventory/NOPE").status_code == 404


def test_negative_stock_rejected(client):
    r = client.post("/inventory", json={"sku": "A1", "name": "Item", "on_hand": -1})
    assert r.status_code == 422


def test_cannot_lower_stock_below_reserved(stocked):
    from tests.conftest import order_body

    stocked.post("/orders", json=order_body([{"sku": "WMT-1001", "quantity": 6, "unit_price": 5}]))
    r = stocked.post("/inventory", json={"sku": "WMT-1001", "name": "Rice 5kg", "on_hand": 4})
    assert r.status_code == 409


def test_list_inventory(stocked):
    skus = [i["sku"] for i in stocked.get("/inventory").json()]
    assert skus == ["WMT-1001", "WMT-1002"]
