import importlib

from fastapi.testclient import TestClient


def test_notification_updates_are_idempotent_in_local_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "notifications.db"))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_HOST", "")
    monkeypatch.setenv("DATABASE_SCHEMA_BOOTSTRAP", "true")

    from app import main

    notification_service = importlib.reload(main)
    client = TestClient(notification_service.app)
    payload = {
        "order_id": "test-order",
        "customer_name": "Test Customer",
        "message": "Order placed",
    }

    assert client.get("/ready").status_code == 200
    first = client.post("/notifications/order-updates", json=payload)
    retry = client.post("/notifications/order-updates", json=payload)

    assert first.status_code == retry.status_code == 201
    assert first.json()["notification_id"] == retry.json()["notification_id"]
    assert len(client.get("/notifications").json()) == 1
