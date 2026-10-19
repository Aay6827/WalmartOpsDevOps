def test_live(client):
    assert client.get("/health/live").json() == {"status": "alive"}


def test_ready(client):
    body = client.get("/health/ready").json()
    assert body["status"] == "ready"
    assert body["service"] == "fulfilment-api"


def test_metrics_exposes_custom_counters(stocked):
    text = stocked.get("/metrics").text
    assert "orders_created_total" in text
    assert "inventory_low_stock_skus" in text
    assert "http_request_duration_seconds" in text
