from app.database import get_db
from app.main import app


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


def test_metrics_keeps_serving_when_database_is_down(client):
    app.dependency_overrides[get_db] = broken_db
    try:
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "db_up 0.0" in r.text
    finally:
        app.dependency_overrides.clear()

    r = client.get("/metrics")
    assert r.status_code == 200
    assert "db_up 1.0" in r.text


def test_readiness_reports_503_when_database_is_down(client):
    app.dependency_overrides[get_db] = broken_db
    try:
        assert client.get("/health/ready").status_code == 503
    finally:
        app.dependency_overrides.clear()
    assert client.get("/health/ready").status_code == 200