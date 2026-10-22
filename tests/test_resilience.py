from fastapi.routing import APIRoute

from app.database import SessionLocal, get_db
from app.main import app
from app.probe import refresh_db_gauges


class BrokenSession:
    """Stands in for a SQLAlchemy session whose database is unreachable."""

    def query(self, *args, **kwargs):
        raise RuntimeError("database unreachable")

    def execute(self, *args, **kwargs):
        raise RuntimeError("database unreachable")

    def rollback(self):
        pass

    def close(self):
        pass


def broken_db():
    yield BrokenSession()


def test_metrics_route_has_no_database_dependency():
    route = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == "/metrics")
    assert route.dependant.dependencies == []


def test_probe_reports_database_down_then_up(client):
    assert refresh_db_gauges(lambda: BrokenSession()) is False
    assert "db_up 0.0" in client.get("/metrics").text

    assert refresh_db_gauges(SessionLocal) is True
    assert "db_up 1.0" in client.get("/metrics").text


def test_readiness_reports_503_when_database_is_down(client):
    app.dependency_overrides[get_db] = broken_db
    try:
        assert client.get("/health/ready").status_code == 503
    finally:
        app.dependency_overrides.clear()
    assert client.get("/health/ready").status_code == 200