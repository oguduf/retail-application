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
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row


app = FastAPI(title="Coffee Notification Service")
DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/notifications.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")
DATABASE_HOST = os.getenv("DATABASE_HOST", "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "orders")
DATABASE_USER = os.getenv("DATABASE_USER", "notifications_app")
DATABASE_SCHEMA = os.getenv("DATABASE_SCHEMA", "notifications")
DATABASE_IAM_AUTH = os.getenv("DATABASE_IAM_AUTH", "false").lower() == "true"
DATABASE_SCHEMA_BOOTSTRAP = os.getenv("DATABASE_SCHEMA_BOOTSTRAP", "true").lower() == "true"
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")
logger = logging.getLogger(__name__)
sqs = boto3.client("sqs") if SQS_QUEUE_URL else None
sns = boto3.client("sns") if SNS_TOPIC_ARN else None


class OrderUpdate(BaseModel):
    order_id: str
    customer_name: str
    message: str = Field(min_length=1, max_length=500)


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


@app.get("/ready")
def readiness_check():
    try:
        with closing(connect()) as connection:
            execute(connection, "SELECT 1")
    except (sqlite3.Error, psycopg.Error) as error:
        raise HTTPException(status_code=503, detail="Notification database is unavailable") from error
    return {"status": "ready", "service": "notifications"}


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
        execute(connection,
            """INSERT INTO notifications
            (notification_id, order_id, customer_name, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (order_id, message) DO NOTHING""",
            (notification_id, update.order_id, update.customer_name, update.message, created_at),
        )
        row = execute(connection,
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
        rows = execute(connection,
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return [dict(row) for row in rows]
