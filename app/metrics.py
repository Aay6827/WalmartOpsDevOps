from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency in seconds", ["method", "path"]
)
ORDERS_CREATED = Counter("orders_created_total", "Orders created", ["channel"])
ORDER_STATUS_CHANGES = Counter(
    "order_status_changes_total", "Order status transitions", ["to_status"]
)
RESERVATION_FAILURES = Counter(
    "inventory_reservation_failures_total", "Orders rejected for insufficient stock"
)
LOW_STOCK_SKUS = Gauge("inventory_low_stock_skus", "SKUs at or below the low-stock threshold")
DB_UP = Gauge("db_up", "1 if the database answered the last probe, else 0")
