import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone

import boto3
from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(title="Coffee Notification Service")
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/notifications.db")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")
logger = logging.getLogger(__name__)
sqs = boto3.client("sqs") if SQS_QUEUE_URL else None
sns = boto3.client("sns") if SNS_TOPIC_ARN else None


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


@app.on_event("startup")
def start_order_notification_consumer():
    if SQS_QUEUE_URL or SNS_TOPIC_ARN:
        if not (SQS_QUEUE_URL and SNS_TOPIC_ARN):
            raise RuntimeError("SQS_QUEUE_URL and SNS_TOPIC_ARN must be configured together")
        threading.Thread(
            target=consume_order_notifications,
            name="order-notification-consumer",
            daemon=True,
        ).start()


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


def consume_order_notifications():
    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
                VisibilityTimeout=60,
            )
            for message in response.get("Messages", []):
                process_order_message(message)
        except Exception:
            logger.exception("Order notification queue poll failed")
            time.sleep(5)


def process_order_message(message):
    try:
        envelope = json.loads(message["Body"])
        event = envelope.get("detail", envelope)
        order_id = event["orderId"]
        customer_name = event["customerName"]
        product_name = event["productName"]
        quantity = int(event["quantity"])
        total = float(event["total"])
        notification = record_order_update(
            OrderUpdate(
                order_id=order_id,
                customer_name=customer_name,
                message=f"Your order for {quantity} x {product_name} was placed.",
            )
        )

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"Roast & Relay order {order_id[:8]} placed",
            Message=(
                f"Hi {customer_name}, your order for {quantity} x {product_name} "
                f"was placed successfully. Order {order_id}. Total: ${total:.2f}."
            ),
            MessageAttributes={
                "orderId": {"DataType": "String", "StringValue": order_id},
                "notificationId": {"DataType": "String", "StringValue": notification["notification_id"]},
            },
        )
        sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=message["ReceiptHandle"])
        logger.info("Processed order notification for %s", order_id)
    except Exception:
        logger.exception("Could not process order notification message %s", message.get("MessageId", "unknown"))


@app.get("/notifications")
def list_notifications():
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return [dict(row) for row in rows]
