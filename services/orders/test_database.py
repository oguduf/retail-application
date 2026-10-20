import importlib
import sqlite3

import httpx

from fastapi.testclient import TestClient


def test_order_service_uses_local_sqlite_without_aws_credentials(tmp_path, monkeypatch):
    database_path = tmp_path / "orders.db"
    with sqlite3.connect(database_path) as legacy_connection:
        legacy_connection.execute(
            """CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                sku TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price DOUBLE PRECISION NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
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
            """INSERT INTO orders
               (order_id, customer_name, sku, product_name, quantity, unit_price, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("test-order", "Test Customer", "sku-1", "Test Coffee", 1, 12.5, "PLACED", "2026-01-01T00:00:00+00:00"),
        )
        connection.commit()

    response = client.get("/orders/test-order")
    assert response.status_code == 200
    assert response.json()["total"] == 12.5
    assert response.json()["bag_size"] == "12 oz"
    assert response.json()["grind"] == "Whole bean"

    def catalog_response(*args, **kwargs):
        return httpx.Response(200, json={
            "sku": "sku-1",
            "name": "Test Coffee",
            "price": 12.5,
            "size_prices": {"12 oz": 12.5, "2 lb": 29.99},
        })

    def service_response(url, *args, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(201, json={"status": "ok"}, request=request)

    monkeypatch.setattr(order_service.httpx, "get", catalog_response)
    monkeypatch.setattr(order_service.httpx, "post", service_response)
    placed = client.post("/orders", json={
        "customer_name": "Test Customer",
        "sku": "sku-1",
        "quantity": 2,
        "bag_size": "2 lb",
        "grind": "French press",
    })
    assert placed.status_code == 201
    assert placed.json()["unit_price"] == 29.99
    assert placed.json()["total"] == 59.98
    assert placed.json()["bag_size"] == "2 lb"
    assert placed.json()["grind"] == "French press"
