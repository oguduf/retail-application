import importlib

from fastapi.testclient import TestClient


def test_order_service_uses_local_sqlite_without_aws_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "orders.db"))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_HOST", "")
    monkeypatch.setenv("DATABASE_SCHEMA_BOOTSTRAP", "true")
    monkeypatch.setenv("EVENT_BUS_NAME", "")

    from app import main

    order_service = importlib.reload(main)
    client = TestClient(order_service.app)

    assert client.get("/ready").status_code == 200

    with order_service.connect() as connection:
        order_service.execute(
            connection,
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("test-order", "Test Customer", "sku-1", "Test Coffee", 1, 12.5, "PLACED", "2026-01-01T00:00:00+00:00"),
        )
        connection.commit()

    response = client.get("/orders/test-order")
    assert response.status_code == 200
    assert response.json()["total"] == 12.5
