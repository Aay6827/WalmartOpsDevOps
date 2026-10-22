import logging
import threading

from sqlalchemy import func, text

from app import metrics
from app.config import LOW_STOCK_THRESHOLD
from app.database import SessionLocal
from app.models import InventoryItem

log = logging.getLogger("fulfilment.probe")
_last_up = {"value": None}


def refresh_db_gauges(session_factory=SessionLocal) -> bool:
    """Probe the database once and update db_up and the low-stock gauge. Never raises."""
    db = None
    up = False
    try:
        db = session_factory()
        db.execute(text("SELECT 1"))
        low = (
            db.query(func.count())
            .select_from(InventoryItem)
            .filter((InventoryItem.on_hand - InventoryItem.reserved) <= LOW_STOCK_THRESHOLD)
            .scalar()
        )
        metrics.LOW_STOCK_SKUS.set(low or 0)
        up = True
        detail = "ok"
    except Exception as exc:
        detail = exc.__class__.__name__
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    metrics.DB_UP.set(1 if up else 0)
    if _last_up["value"] is not up:
        log.log(logging.INFO if up else logging.WARNING, "database probe state changed: up=%s (%s)", up, detail)
        _last_up["value"] = up
    return up


def start_probe(interval: float = 5.0) -> threading.Event:
    """Run the probe in a daemon thread. Set the returned event to stop it."""
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            refresh_db_gauges()
            stop.wait(interval)

    threading.Thread(target=loop, name="db-probe", daemon=True).start()
    return stop