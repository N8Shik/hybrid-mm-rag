from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from pathlib import Path


TABLE_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

SAMPLE_TABLE_FILES = {
    "customers": "sample_customers.csv",
    "orders": "sample_orders.csv",
    "order_items": "sample_items.csv",
    "products": "sample_products.csv",
}

TABLE_COLUMNS = {
    "customers": [
        ("customer_id", "TEXT PRIMARY KEY"),
        ("customer_unique_id", "TEXT NOT NULL"),
        ("customer_zip_code_prefix", "TEXT"),
        ("customer_city", "TEXT"),
        ("customer_state", "TEXT"),
    ],
    "geolocation": [
        ("geolocation_zip_code_prefix", "TEXT"),
        ("geolocation_lat", "REAL"),
        ("geolocation_lng", "REAL"),
        ("geolocation_city", "TEXT"),
        ("geolocation_state", "TEXT"),
    ],
    "order_items": [
        ("order_id", "TEXT"),
        ("order_item_id", "INTEGER"),
        ("product_id", "TEXT"),
        ("seller_id", "TEXT"),
        ("shipping_limit_date", "TEXT"),
        ("price", "REAL"),
        ("freight_value", "REAL"),
    ],
    "payments": [
        ("order_id", "TEXT"),
        ("payment_sequential", "INTEGER"),
        ("payment_type", "TEXT"),
        ("payment_installments", "INTEGER"),
        ("payment_value", "REAL"),
    ],
    "reviews": [
        ("review_id", "TEXT"),
        ("order_id", "TEXT"),
        ("review_score", "INTEGER"),
        ("review_comment_title", "TEXT"),
        ("review_comment_message", "TEXT"),
        ("review_creation_date", "TEXT"),
        ("review_answer_timestamp", "TEXT"),
    ],
    "orders": [
        ("order_id", "TEXT PRIMARY KEY"),
        ("customer_id", "TEXT NOT NULL"),
        ("order_status", "TEXT"),
        ("order_purchase_timestamp", "TEXT"),
        ("order_approved_at", "TEXT"),
        ("order_delivered_carrier_date", "TEXT"),
        ("order_delivered_customer_date", "TEXT"),
        ("order_estimated_delivery_date", "TEXT"),
    ],
    "products": [
        ("product_id", "TEXT PRIMARY KEY"),
        ("product_category_name", "TEXT"),
        ("product_name_lenght", "INTEGER"),
        ("product_description_lenght", "INTEGER"),
        ("product_photos_qty", "INTEGER"),
        ("product_weight_g", "REAL"),
        ("product_length_cm", "REAL"),
        ("product_height_cm", "REAL"),
        ("product_width_cm", "REAL"),
    ],
    "sellers": [
        ("seller_id", "TEXT PRIMARY KEY"),
        ("seller_zip_code_prefix", "TEXT"),
        ("seller_city", "TEXT"),
        ("seller_state", "TEXT"),
    ],
    "category_translation": [
        ("product_category_name", "TEXT PRIMARY KEY"),
        ("product_category_name_english", "TEXT"),
    ],
}

NUMERIC_COLUMNS = {
    name
    for columns in TABLE_COLUMNS.values()
    for name, sql_type in columns
    if "REAL" in sql_type or "INTEGER" in sql_type
}


def required_files(data_dir: Path, mode: str = "full") -> list[Path]:
    files = TABLE_FILES if mode == "full" else SAMPLE_TABLE_FILES
    return [data_dir / filename for filename in files.values()]


def validate_dataset(data_dir: Path, mode: str = "full") -> dict[str, int]:
    if mode not in {"full", "sample"}:
        raise ValueError("mode must be 'full' or 'sample'")
    source_files = TABLE_FILES if mode == "full" else SAMPLE_TABLE_FILES
    missing = [path.name for path in required_files(data_dir, mode) if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing Olist CSV files: " + ", ".join(sorted(missing))
        )

    counts: dict[str, int] = {}
    for table, filename in source_files.items():
        with (data_dir / filename).open("r", encoding="utf-8-sig", newline="") as handle:
            counts[table] = max(sum(1 for _ in handle) - 1, 0)
    return counts


def _convert(value: str | None, column: str):
    if value is None or value == "":
        return None
    if column in NUMERIC_COLUMNS:
        if "_id" not in column and column.endswith("_id") is False:
            try:
                if column in {"order_item_id", "payment_sequential", "payment_installments", "review_score", "product_name_lenght", "product_description_lenght", "product_photos_qty"}:
                    return int(value)
                return float(value)
            except ValueError:
                return None
    return value


def _create_tables(connection: sqlite3.Connection) -> None:
    for table, columns in TABLE_COLUMNS.items():
        definition = ", ".join(f'"{name}" {sql_type}' for name, sql_type in columns)
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
        connection.execute(f'CREATE TABLE "{table}" ({definition})')


def _rows(path: Path, columns: list[str]) -> Iterable[tuple]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        missing = sorted(set(columns) - set(reader.fieldnames))
        if missing:
            raise ValueError(f"{path.name} is missing columns: {', '.join(missing)}")
        for row in reader:
            yield tuple(_convert(row.get(column), column) for column in columns)


def _load_table(connection: sqlite3.Connection, data_dir: Path, table: str, mode: str) -> int:
    columns = [name for name, _ in TABLE_COLUMNS[table]]
    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(f'"{name}"' for name in columns)
    sql = f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})'
    rows_loaded = 0
    batch: list[tuple] = []
    filenames = TABLE_FILES if mode == "full" else SAMPLE_TABLE_FILES
    for row in _rows(data_dir / filenames[table], columns):
        batch.append(row)
        if len(batch) == 5_000:
            connection.executemany(sql, batch)
            rows_loaded += len(batch)
            batch.clear()
    if batch:
        connection.executemany(sql, batch)
        rows_loaded += len(batch)
    return rows_loaded


def _create_views(connection: sqlite3.Connection) -> None:
    statements = [
        "DROP VIEW IF EXISTS order_items_enriched",
        "DROP VIEW IF EXISTS order_summary",
        "DROP VIEW IF EXISTS category_sales",
        "DROP VIEW IF EXISTS seller_sales",
        "DROP VIEW IF EXISTS geolocation_summary",
        """
        CREATE VIEW order_items_enriched AS
        SELECT oi.order_id, oi.order_item_id, oi.product_id, oi.seller_id,
               oi.price, oi.freight_value, o.customer_id, o.order_status,
               o.order_purchase_timestamp, o.order_delivered_customer_date,
               o.order_estimated_delivery_date,
               p.product_category_name,
               COALESCE(t.product_category_name_english, p.product_category_name) AS category_name,
               s.seller_state
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        LEFT JOIN products p ON p.product_id = oi.product_id
        LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
        LEFT JOIN sellers s ON s.seller_id = oi.seller_id
        """,
        """
        CREATE VIEW order_summary AS
        SELECT o.order_id, o.customer_id, o.order_status,
               o.order_purchase_timestamp, o.order_delivered_customer_date,
               o.order_estimated_delivery_date,
               ROUND(SUM(oi.price), 2) AS item_revenue,
               ROUND(SUM(oi.freight_value), 2) AS freight_revenue,
               ROUND(SUM(oi.price + oi.freight_value), 2) AS order_value,
               ROUND(julianday(o.order_delivered_customer_date) - julianday(o.order_estimated_delivery_date), 2) AS delivery_delay_days
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.order_id
        GROUP BY o.order_id
        """,
        """
        CREATE VIEW category_sales AS
        SELECT category_name,
               COUNT(DISTINCT order_id) AS order_count,
               SUM(price) AS item_revenue,
               SUM(freight_value) AS freight_revenue
        FROM order_items_enriched
        GROUP BY category_name
        """,
        """
        CREATE VIEW seller_sales AS
        SELECT seller_id, seller_state,
               COUNT(DISTINCT order_id) AS order_count,
               SUM(price) AS item_revenue,
               SUM(freight_value) AS freight_revenue
        FROM order_items_enriched
        GROUP BY seller_id, seller_state
        """,
        """
        CREATE VIEW geolocation_summary AS
        SELECT geolocation_zip_code_prefix,
               AVG(geolocation_lat) AS latitude,
               AVG(geolocation_lng) AS longitude,
               MAX(geolocation_city) AS city,
               MAX(geolocation_state) AS state,
               COUNT(*) AS source_rows
        FROM geolocation
        GROUP BY geolocation_zip_code_prefix
        """,
    ]
    for statement in statements:
        connection.execute(statement)


def _derive_sample_sellers(connection: sqlite3.Connection, data_dir: Path) -> int:
    """Insert one seller row per seller_id referenced by the sample order_items.

    The four-file reduced sample has no sample_sellers.csv, so seller location
    columns are NULL by default. When the full Olist seller file is available
    alongside the sample (as it is when the archive was downloaded in "full"
    mode too), enrich each sampled seller with its real zip/city/state instead
    of leaving those columns permanently empty.
    """
    rows = connection.execute(
        """
        INSERT INTO sellers (seller_id)
        SELECT DISTINCT seller_id FROM order_items
        WHERE seller_id IS NOT NULL
        """
    ).rowcount

    full_sellers_path = data_dir / TABLE_FILES["sellers"]
    if full_sellers_path.is_file():
        with full_sellers_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            updates = [
                (row.get("seller_zip_code_prefix"), row.get("seller_city"), row.get("seller_state"), row["seller_id"])
                for row in reader
            ]
        connection.executemany(
            """
            UPDATE sellers
            SET seller_zip_code_prefix = ?, seller_city = ?, seller_state = ?
            WHERE seller_id = ?
            """,
            updates,
        )
    return rows


def build_sqlite(data_dir: Path, sqlite_path: Path, mode: str = "full") -> dict[str, int]:
    data_dir = Path(data_dir)
    sqlite_path = Path(sqlite_path)
    validate_dataset(data_dir, mode)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if sqlite_path.exists():
        sqlite_path.unlink()

    connection = sqlite3.connect(sqlite_path)
    try:
        _create_tables(connection)
        if mode == "full":
            counts = {table: _load_table(connection, data_dir, table, mode) for table in TABLE_FILES}
        else:
            counts = {table: 0 for table in TABLE_FILES}
            for table in SAMPLE_TABLE_FILES:
                counts[table] = _load_table(connection, data_dir, table, mode)
            counts["sellers"] = _derive_sample_sellers(connection, data_dir)
        _create_views(connection)
        connection.execute("CREATE INDEX idx_order_items_order ON order_items(order_id)")
        connection.execute("CREATE INDEX idx_order_items_product ON order_items(product_id)")
        connection.execute("CREATE INDEX idx_order_items_seller ON order_items(seller_id)")
        connection.execute("CREATE INDEX idx_orders_customer ON orders(customer_id)")
        connection.execute("CREATE INDEX idx_customers_unique ON customers(customer_unique_id)")
        connection.commit()
        return counts
    finally:
        connection.close()
