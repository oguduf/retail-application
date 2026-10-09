import importlib

from fastapi.testclient import TestClient


def test_inventory_reservations_are_idempotent_in_local_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "inventory.db"))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_HOST", "")
    monkeypatch.setenv("DATABASE_SCHEMA_BOOTSTRAP", "true")

    from app import main

    inventory_service = importlib.reload(main)
    client = TestClient(inventory_service.app)

    assert client.get("/ready").status_code == 200
    first = client.post(
        "/inventory/reservations",
        json={"order_id": "test-order", "sku": "ETHIOPIA-YIRGACHEFFE", "quantity": 2},
    )
    retry = client.post(
        "/inventory/reservations",
        json={"order_id": "test-order", "sku": "ETHIOPIA-YIRGACHEFFE", "quantity": 2},
    )

    assert first.status_code == 201
    assert retry.status_code == 201
    assert first.json()["available"] == retry.json()["available"] == 16
    assert client.get("/inventory/ETHIOPIA-YIRGACHEFFE").json()["quantity"] == 16
