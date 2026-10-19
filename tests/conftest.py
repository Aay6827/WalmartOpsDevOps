import os

os.environ["DATABASE_URL"] = "sqlite:///./test_walmartops.db"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def stocked(client):
    client.post("/inventory", json={"sku": "WMT-1001", "name": "Rice 5kg", "on_hand": 10})
    client.post("/inventory", json={"sku": "WMT-1002", "name": "Olive Oil 1L", "on_hand": 3})
    return client


def order_body(lines, channel="online"):
    return {"customer_id": "C-001", "channel": channel, "lines": lines}
