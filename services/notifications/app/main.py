import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(title="Coffee Notification Service")
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/notifications.db")


class OrderUpdate(BaseModel):
    order_id: str
    customer_name: str
    message: str = Field(min_length=1, max_length=500)


def connect():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(connect()) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS notifications (
                notification_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (order_id, message)
            )"""
        )
        connection.commit()


initialize_database()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "notifications"}


@app.post("/notifications/order-updates", status_code=201)
def record_order_update(update: OrderUpdate):
    notification_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(connect()) as connection:
        connection.execute(
            """INSERT OR IGNORE INTO notifications
            (notification_id, order_id, customer_name, message, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (notification_id, update.order_id, update.customer_name, update.message, created_at),
        )
        row = connection.execute(
            "SELECT * FROM notifications WHERE order_id = ? AND message = ?",
            (update.order_id, update.message),
        ).fetchone()
        connection.commit()
    return dict(row)


@app.get("/notifications")
def list_notifications():
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return [dict(row) for row in rows]
