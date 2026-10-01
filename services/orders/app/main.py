import logging
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Coffee Order Service")
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/orders.db")
CATALOG_URL = os.getenv("CATALOG_URL", "http://product-service:8000")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://inventory-service:8000")
NOTIFICATIONS_URL = os.getenv("NOTIFICATIONS_URL", "http://notification-service:8000")


class CreateOrderRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    sku: str = Field(min_length=1, max_length=80)
    quantity: int = Field(gt=0, le=20)


def connect():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(connect()) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                sku TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        connection.commit()


initialize_database()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "orders"}


@app.post("/orders", status_code=201)
def create_order(request: CreateOrderRequest):
    order_id = str(uuid.uuid4())

    try:
        product_response = httpx.get(f"{CATALOG_URL}/products/{request.sku}", timeout=3)
    except httpx.RequestError as error:
        raise HTTPException(status_code=503, detail="Product catalog is temporarily unavailable") from error

    if product_response.status_code == 404:
        raise HTTPException(status_code=404, detail="Product not found")
    if product_response.is_error:
        raise HTTPException(status_code=503, detail="Product catalog could not validate this order")

    product = product_response.json()

    try:
        inventory_response = httpx.post(
            f"{INVENTORY_URL}/inventory/reservations",
            json={"order_id": order_id, "sku": request.sku, "quantity": request.quantity},
            timeout=3,
        )
    except httpx.RequestError as error:
        raise HTTPException(status_code=503, detail="Inventory service is temporarily unavailable") from error

    if inventory_response.status_code == 409:
        raise HTTPException(status_code=409, detail="Not enough coffee in stock")
    if inventory_response.status_code == 404:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if inventory_response.is_error:
        raise HTTPException(status_code=503, detail="Inventory service could not reserve this order")

    order = {
        "order_id": order_id,
        "customer_name": request.customer_name,
        "sku": request.sku,
        "product_name": product["name"],
        "quantity": request.quantity,
        "unit_price": product["price"],
        "status": "PLACED",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        with closing(connect()) as connection:
            connection.execute(
                """INSERT INTO orders
                (order_id, customer_name, sku, product_name, quantity, unit_price, status, created_at)
                VALUES (:order_id, :customer_name, :sku, :product_name, :quantity, :unit_price, :status, :created_at)""",
                order,
            )
            connection.commit()
    except sqlite3.Error as error:
        try:
            httpx.post(
                f"{INVENTORY_URL}/inventory/reservations/release",
                json={"order_id": order_id},
                timeout=3,
            )
        except httpx.RequestError:
            logger.exception("Order storage failed and inventory compensation also failed for %s", order_id)
        raise HTTPException(status_code=503, detail="Order could not be saved; inventory release was requested") from error

    try:
        notification_response = httpx.post(
            f"{NOTIFICATIONS_URL}/notifications/order-updates",
            json={
                "order_id": order_id,
                "customer_name": request.customer_name,
                "message": f"Your order for {request.quantity} x {product['name']} was placed.",
            },
            timeout=2,
        )
        notification_response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Order %s was placed, but notification delivery is currently unavailable", order_id)

    return {**order, "total": round(request.quantity * product["price"], 2)}


@app.get("/orders")
def list_orders():
    with closing(connect()) as connection:
        rows = connection.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50").fetchall()
    return [dict(row) | {"total": round(row["quantity"] * row["unit_price"], 2)} for row in rows]


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    order = dict(row)
    order["total"] = round(order["quantity"] * order["unit_price"], 2)
    return order
