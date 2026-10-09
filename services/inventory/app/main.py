import os
import sqlite3
from contextlib import closing

import boto3
import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from pydantic import BaseModel, Field


app = FastAPI(title="Coffee Inventory Service")
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/inventory.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")
DATABASE_HOST = os.getenv("DATABASE_HOST", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "orders")
DATABASE_USER = os.getenv("DATABASE_USER", "inventory_app")
DATABASE_SCHEMA = os.getenv("DATABASE_SCHEMA", "inventory")
DATABASE_IAM_AUTH = os.getenv("DATABASE_IAM_AUTH", "false").lower() == "true"
DATABASE_SCHEMA_BOOTSTRAP = os.getenv("DATABASE_SCHEMA_BOOTSTRAP", "true").lower() == "true"
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
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


def get_database_conninfo():
    if DATABASE_URL:
        return DATABASE_URL
    if not DATABASE_HOST:
        return ""
    return make_conninfo(
        host=DATABASE_HOST,
        port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=DATABASE_NAME,
        user=DATABASE_USER,
        options=f"-c search_path={DATABASE_SCHEMA},public",
        sslmode="require",
    )


POSTGRES_CONNINFO = get_database_conninfo()
USING_POSTGRES = bool(POSTGRES_CONNINFO)


def connect():
    if USING_POSTGRES:
        parameters = {"row_factory": dict_row, "connect_timeout": 5}
        if DATABASE_IAM_AUTH:
            parameters["password"] = boto3.client("rds", region_name=AWS_REGION).generate_db_auth_token(
                DBHostname=DATABASE_HOST,
                Port=int(os.getenv("DATABASE_PORT", "5432")),
                DBUsername=DATABASE_USER,
                Region=AWS_REGION,
            )
        return psycopg.connect(POSTGRES_CONNINFO, **parameters)
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def execute(connection, statement, parameters=()):
    if USING_POSTGRES:
        statement = statement.replace("?", "%s")
    return connection.execute(statement, parameters)


def initialize_database():
    if not DATABASE_SCHEMA_BOOTSTRAP:
        return
    with closing(connect()) as connection:
        execute(connection,
            "CREATE TABLE IF NOT EXISTS stock (sku TEXT PRIMARY KEY, quantity INTEGER NOT NULL CHECK(quantity >= 0))"
        )
        execute(connection,
            """CREATE TABLE IF NOT EXISTS reservations (
                order_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                PRIMARY KEY (order_id, sku)
            )"""
        )
        for sku, quantity in INITIAL_STOCK.items():
            execute(connection,
                "INSERT INTO stock (sku, quantity) VALUES (?, ?) ON CONFLICT (sku) DO NOTHING", (sku, quantity)
            )
        connection.commit()


initialize_database()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "inventory"}


@app.get("/ready")
def readiness_check():
    try:
        with closing(connect()) as connection:
            execute(connection, "SELECT 1")
    except (sqlite3.Error, psycopg.Error) as error:
        raise HTTPException(status_code=503, detail="Inventory database is unavailable") from error
    return {"status": "ready", "service": "inventory"}


@app.get("/inventory")
def list_inventory():
    with closing(connect()) as connection:
        rows = execute(connection, "SELECT sku, quantity FROM stock ORDER BY sku").fetchall()
    return [dict(row) for row in rows]


@app.get("/inventory/{sku}")
def get_inventory(sku: str):
    with closing(connect()) as connection:
        row = execute(connection, "SELECT sku, quantity FROM stock WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return dict(row)


@app.post("/inventory/reservations", status_code=201)
def reserve_inventory(request: ReservationRequest):
    with closing(connect()) as connection:
        try:
            if not USING_POSTGRES:
                connection.execute("BEGIN IMMEDIATE")
            existing = execute(connection,
                "SELECT quantity FROM reservations WHERE order_id = ? AND sku = ?",
                (request.order_id, request.sku),
            ).fetchone()
            if existing:
                if existing["quantity"] != request.quantity:
                    raise HTTPException(status_code=409, detail="Order already has a different reservation")
                stock = execute(connection,
                    "SELECT quantity FROM stock WHERE sku = ?", (request.sku,)
                ).fetchone()
                connection.commit()
                return {"reserved": True, "sku": request.sku, "available": stock["quantity"]}

            reservation_cursor = execute(
                connection,
                "INSERT INTO reservations (order_id, sku, quantity) VALUES (?, ?, ?) ON CONFLICT (order_id, sku) DO NOTHING",
                (request.order_id, request.sku, request.quantity),
            )
            if reservation_cursor.rowcount == 0:
                existing = execute(connection,
                    "SELECT quantity FROM reservations WHERE order_id = ? AND sku = ?",
                    (request.order_id, request.sku),
                ).fetchone()
                if existing["quantity"] != request.quantity:
                    raise HTTPException(status_code=409, detail="Order already has a different reservation")
                stock = execute(connection,
                    "SELECT quantity FROM stock WHERE sku = ?", (request.sku,)
                ).fetchone()
                connection.commit()
                return {"reserved": True, "sku": request.sku, "available": stock["quantity"]}

            cursor = execute(connection,
                "UPDATE stock SET quantity = quantity - ? WHERE sku = ? AND quantity >= ?",
                (request.quantity, request.sku, request.quantity),
            )
            if cursor.rowcount != 1:
                exists = execute(connection,
                    "SELECT 1 FROM stock WHERE sku = ?", (request.sku,)
                ).fetchone()
                connection.rollback()
                if exists is None:
                    raise HTTPException(status_code=404, detail="Inventory item not found")
                raise HTTPException(status_code=409, detail="Insufficient stock")

            remaining = execute(connection,
                "SELECT quantity FROM stock WHERE sku = ?", (request.sku,)
            ).fetchone()["quantity"]
            connection.commit()
            return {"reserved": True, "sku": request.sku, "available": remaining}
        except HTTPException:
            connection.rollback()
            raise
        except (sqlite3.Error, psycopg.Error) as error:
            connection.rollback()
            raise HTTPException(status_code=503, detail="Inventory storage is unavailable") from error


@app.post("/inventory/reservations/release")
def release_inventory(request: ReleaseRequest):
    with closing(connect()) as connection:
        try:
            if not USING_POSTGRES:
                connection.execute("BEGIN IMMEDIATE")
            reservations = execute(connection,
                "SELECT sku, quantity FROM reservations WHERE order_id = ?", (request.order_id,)
            ).fetchall()
            for reservation in reservations:
                execute(connection,
                    "UPDATE stock SET quantity = quantity + ? WHERE sku = ?",
                    (reservation["quantity"], reservation["sku"]),
                )
            execute(connection, "DELETE FROM reservations WHERE order_id = ?", (request.order_id,))
            connection.commit()
            return {"released": bool(reservations), "order_id": request.order_id}
        except (sqlite3.Error, psycopg.Error) as error:
            connection.rollback()
            raise HTTPException(status_code=503, detail="Inventory storage is unavailable") from error
