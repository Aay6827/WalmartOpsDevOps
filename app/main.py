import time
from collections import defaultdict
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import metrics
from app.config import APP_VERSION, LOW_STOCK_THRESHOLD, SERVICE_NAME
from app.database import Base, engine, get_db
from app.models import InventoryItem, Order, OrderLine
from app.schemas import (
    InventoryOut,
    InventoryUpsert,
    OrderCreate,
    OrderOut,
    StatusUpdate,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Walmart Fulfilment API", version=APP_VERSION)

TRANSITIONS = {
    "CREATED": {"PICKING", "CANCELLED"},
    "PICKING": {"PACKED", "CANCELLED"},
    "PACKED": {"SHIPPED", "CANCELLED"},
    "SHIPPED": {"DELIVERED"},
    "DELIVERED": set(),
    "CANCELLED": set(),
}


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = route.path if route else "unmatched"
    if path != "/metrics":
        metrics.HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        metrics.HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
    return response


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ready", "service": SERVICE_NAME, "version": APP_VERSION}


@app.get("/metrics")
def prometheus_metrics(db: Session = Depends(get_db)):
    low = (
        db.query(func.count())
        .select_from(InventoryItem)
        .filter((InventoryItem.on_hand - InventoryItem.reserved) <= LOW_STOCK_THRESHOLD)
        .scalar()
    )
    metrics.LOW_STOCK_SKUS.set(low or 0)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/inventory", response_model=InventoryOut, status_code=201)
def upsert_inventory(payload: InventoryUpsert, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, payload.sku)
    if item is None:
        item = InventoryItem(**payload.model_dump())
        db.add(item)
    else:
        if payload.on_hand < item.reserved:
            raise HTTPException(status_code=409, detail="on_hand cannot be below reserved units")
        item.name = payload.name
        item.store_id = payload.store_id
        item.on_hand = payload.on_hand
    db.commit()
    db.refresh(item)
    return item


@app.get("/inventory", response_model=list[InventoryOut])
def list_inventory(db: Session = Depends(get_db)):
    return db.query(InventoryItem).order_by(InventoryItem.sku).all()


@app.get("/inventory/{sku}", response_model=InventoryOut)
def get_inventory(sku: str, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, sku)
    if item is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    return item


@app.post("/orders", response_model=OrderOut, status_code=201)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    wanted = defaultdict(int)
    for line in payload.lines:
        wanted[line.sku] += line.quantity

    items = {}
    for sku, qty in wanted.items():
        item = db.get(InventoryItem, sku)
        if item is None:
            raise HTTPException(status_code=404, detail=f"SKU {sku} not found")
        if item.available < qty:
            metrics.RESERVATION_FAILURES.inc()
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient stock for {sku}: requested {qty}, available {item.available}",
            )
        items[sku] = item

    for sku, qty in wanted.items():
        items[sku].reserved += qty

    order = Order(
        customer_id=payload.customer_id,
        channel=payload.channel,
        status="CREATED",
        total=round(sum(l.quantity * l.unit_price for l in payload.lines), 2),
        lines=[OrderLine(**l.model_dump()) for l in payload.lines],
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    metrics.ORDERS_CREATED.labels(payload.channel).inc()
    return order


@app.get("/orders", response_model=list[OrderOut])
def list_orders(status: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Order)
    if status:
        query = query.filter(Order.status == status.upper())
    return query.order_by(Order.id.desc()).limit(min(limit, 200)).all()


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.patch("/orders/{order_id}/status", response_model=OrderOut)
def update_status(order_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if payload.status not in TRANSITIONS[order.status]:
        raise HTTPException(
            status_code=409, detail=f"Cannot move order from {order.status} to {payload.status}"
        )

    for line in order.lines:
        item = db.get(InventoryItem, line.sku)
        if payload.status == "CANCELLED":
            item.reserved -= line.quantity
        elif payload.status == "SHIPPED":
            item.reserved -= line.quantity
            item.on_hand -= line.quantity

    order.status = payload.status
    db.commit()
    db.refresh(order)
    metrics.ORDER_STATUS_CHANGES.labels(payload.status).inc()
    return order
