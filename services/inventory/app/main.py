import os
import sqlite3
from contextlib import closing

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="Coffee Inventory Service")
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/inventory.db")
INITIAL_STOCK = {
    "ETHIOPIA-YIRGACHEFFE": 18,
    "COLOMBIA-HUILA": 24,
    "HOUSE-ESPRESSO": 30,
    "DECAF-COLOMBIA": 12,
}


class ReservationRequest(BaseModel):
    order_id: str
    sku: str
    quantity: int = Field(gt=0, le=20)


class ReleaseRequest(BaseModel):
    order_id: str


def connect():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(connect()) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS stock (sku TEXT PRIMARY KEY, quantity INTEGER NOT NULL CHECK(quantity >= 0))"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS reservations (
                order_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                PRIMARY KEY (order_id, sku)
            )"""
        )
        for sku, quantity in INITIAL_STOCK.items():
            connection.execute(
                "INSERT OR IGNORE INTO stock (sku, quantity) VALUES (?, ?)", (sku, quantity)
            )
        connection.commit()


initialize_database()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "inventory"}


@app.get("/inventory")
def list_inventory():
    with closing(connect()) as connection:
        rows = connection.execute("SELECT sku, quantity FROM stock ORDER BY sku").fetchall()
    return [dict(row) for row in rows]


@app.get("/inventory/{sku}")
def get_inventory(sku: str):
    with closing(connect()) as connection:
        row = connection.execute("SELECT sku, quantity FROM stock WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return dict(row)


@app.post("/inventory/reservations", status_code=201)
def reserve_inventory(request: ReservationRequest):
    with closing(connect()) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT quantity FROM reservations WHERE order_id = ? AND sku = ?",
                (request.order_id, request.sku),
            ).fetchone()
            if existing:
                if existing["quantity"] != request.quantity:
                    raise HTTPException(status_code=409, detail="Order already has a different reservation")
                stock = connection.execute(
                    "SELECT quantity FROM stock WHERE sku = ?", (request.sku,)
                ).fetchone()
                connection.commit()
                return {"reserved": True, "sku": request.sku, "available": stock["quantity"]}

            cursor = connection.execute(
                "UPDATE stock SET quantity = quantity - ? WHERE sku = ? AND quantity >= ?",
                (request.quantity, request.sku, request.quantity),
            )
            if cursor.rowcount != 1:
                exists = connection.execute(
                    "SELECT 1 FROM stock WHERE sku = ?", (request.sku,)
                ).fetchone()
                connection.rollback()
                if exists is None:
                    raise HTTPException(status_code=404, detail="Inventory item not found")
                raise HTTPException(status_code=409, detail="Insufficient stock")

            connection.execute(
                "INSERT INTO reservations (order_id, sku, quantity) VALUES (?, ?, ?)",
                (request.order_id, request.sku, request.quantity),
            )
            remaining = connection.execute(
                "SELECT quantity FROM stock WHERE sku = ?", (request.sku,)
            ).fetchone()["quantity"]
            connection.commit()
            return {"reserved": True, "sku": request.sku, "available": remaining}
        except HTTPException:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as error:
            connection.rollback()
            raise HTTPException(status_code=503, detail="Inventory storage is unavailable") from error


@app.post("/inventory/reservations/release")
def release_inventory(request: ReleaseRequest):
    with closing(connect()) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            reservations = connection.execute(
                "SELECT sku, quantity FROM reservations WHERE order_id = ?", (request.order_id,)
            ).fetchall()
            for reservation in reservations:
                connection.execute(
                    "UPDATE stock SET quantity = quantity + ? WHERE sku = ?",
                    (reservation["quantity"], reservation["sku"]),
                )
            connection.execute("DELETE FROM reservations WHERE order_id = ?", (request.order_id,))
            connection.commit()
            return {"released": bool(reservations), "order_id": request.order_id}
        except sqlite3.Error as error:
            connection.rollback()
            raise HTTPException(status_code=503, detail="Inventory storage is unavailable") from error
