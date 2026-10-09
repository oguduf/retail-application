"""Create application schemas, tables, seed stock, and least-privilege IAM DB roles."""

import json
import os

import boto3
import psycopg
from psycopg.conninfo import make_conninfo


def main():
    secret_response = boto3.client("secretsmanager", region_name=os.environ["AWS_REGION"]).get_secret_value(
        SecretId=os.environ["DATABASE_SECRET_ARN"]
    )
    master = json.loads(secret_response["SecretString"])
    conninfo = make_conninfo(
        host=os.environ["DATABASE_HOST"],
        port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=os.environ["DATABASE_NAME"],
        user=master["username"],
        password=master["password"],
        sslmode="require",
    )

    with psycopg.connect(conninfo, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            for role in ("orders_app", "inventory_app", "notifications_app"):
                cursor.execute(
                    """SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s""",
                    (role,),
                )
                if cursor.fetchone() is None:
                    cursor.execute(f'CREATE ROLE "{role}" LOGIN')
                cursor.execute(f'GRANT rds_iam TO "{role}"')
                cursor.execute(f'GRANT CONNECT ON DATABASE "{os.environ["DATABASE_NAME"]}" TO "{role}"')

            for schema in ("orders", "inventory", "notifications"):
                cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}" AUTHORIZATION CURRENT_USER')

            cursor.execute("SET search_path TO orders")
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS orders (
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
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS event_outbox (
                    event_id TEXT PRIMARY KEY,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT
                )"""
            )
            cursor.execute('GRANT USAGE ON SCHEMA orders TO orders_app')
            cursor.execute("GRANT SELECT, INSERT ON TABLE orders TO orders_app")
            cursor.execute("GRANT SELECT, INSERT, UPDATE ON TABLE event_outbox TO orders_app")
            cursor.execute(
                """ALTER DEFAULT PRIVILEGES IN SCHEMA orders
                   GRANT SELECT, INSERT, UPDATE ON TABLES TO orders_app"""
            )

            cursor.execute("SET search_path TO inventory")
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS stock (
                    sku TEXT PRIMARY KEY,
                    quantity INTEGER NOT NULL CHECK(quantity >= 0)
                )"""
            )
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS reservations (
                    order_id TEXT NOT NULL,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    PRIMARY KEY (order_id, sku)
                )"""
            )
            cursor.executemany(
                "INSERT INTO stock (sku, quantity) VALUES (%s, %s) ON CONFLICT (sku) DO NOTHING",
                [
                    ("ETHIOPIA-YIRGACHEFFE", 18),
                    ("COLOMBIA-HUILA", 24),
                    ("HOUSE-ESPRESSO", 30),
                    ("DECAF-COLOMBIA", 12),
                ],
            )
            cursor.execute('GRANT USAGE ON SCHEMA inventory TO inventory_app')
            cursor.execute("GRANT SELECT ON TABLE stock TO inventory_app")
            cursor.execute("GRANT SELECT, INSERT, DELETE ON TABLE reservations TO inventory_app")
            cursor.execute("GRANT UPDATE (quantity) ON TABLE stock TO inventory_app")
            cursor.execute(
                """ALTER DEFAULT PRIVILEGES IN SCHEMA inventory
                   GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO inventory_app"""
            )

            cursor.execute("SET search_path TO notifications")
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS notifications (
                    notification_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (order_id, message)
                )"""
            )
            cursor.execute('GRANT USAGE ON SCHEMA notifications TO notifications_app')
            cursor.execute("GRANT SELECT, INSERT ON TABLE notifications TO notifications_app")
            cursor.execute(
                """ALTER DEFAULT PRIVILEGES IN SCHEMA notifications
                   GRANT SELECT, INSERT ON TABLES TO notifications_app"""
            )


if __name__ == "__main__":
    main()
