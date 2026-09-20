from __future__ import annotations

import csv
import time
from collections.abc import Iterable
from pathlib import Path

from neo4j import GraphDatabase

from .config import Settings


BATCH_SIZE = 1_000


def _batches(rows: Iterable[dict], size: int = BATCH_SIZE):
    batch: list[dict] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def _read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


class Neo4jStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_environment()
        missing = [name for name, value in {
            "NEO4J_URI": self.settings.neo4j_uri,
            "NEO4J_USERNAME": self.settings.neo4j_username,
            "NEO4J_PASSWORD": self.settings.neo4j_password,
        }.items() if not value]
        if missing:
            raise ValueError("Missing Neo4j settings: " + ", ".join(missing))
        self.driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_username, self.settings.neo4j_password),
        )

    def close(self) -> None:
        self.driver.close()

    def verify_connectivity(self) -> None:
        self.driver.verify_connectivity()

    def execute_read(self, statement: str, parameters: dict | None = None) -> list[dict]:
        records, _, _ = self.driver.execute_query(
            statement,
            parameters_=parameters or {},
            database_=self.settings.neo4j_database,
            routing_="r",
        )
        return [record.data() for record in records]

    def ensure_schema(self) -> None:
        constraints, _, _ = self.driver.execute_query(
            "SHOW CONSTRAINTS", database_=self.settings.neo4j_database
        )
        existing_constraints = [record.data() for record in constraints]
        constraint_specs = [
            ("Customer", "customer_id", "customer_id"),
            ("Order", "order_id", "order_id"),
            ("Product", "product_id", "product_id"),
            ("Seller", "seller_id", "seller_id"),
            ("Category", "name", "category_name"),
            ("Region", "state", "region_state"),
        ]
        for label, property_name, constraint_name in constraint_specs:
            already_exists = any(
                item.get("entityType") == "NODE"
                and item.get("labelsOrTypes") == [label]
                and item.get("properties") == [property_name]
                and item.get("type") in {"UNIQUENESS", "NODE_PROPERTY_UNIQUENESS", "NODE_KEY"}
                for item in existing_constraints
            )
            if already_exists:
                continue
            statement = (
                f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{property_name} IS UNIQUE"
            )
            self.driver.execute_query(statement, database_=self.settings.neo4j_database)

        indexes, _, _ = self.driver.execute_query(
            "SHOW INDEXES", database_=self.settings.neo4j_database
        )
        existing_indexes = [record.data() for record in indexes]
        index_specs = [
            ("Customer", "customer_unique_id", "customer_unique_id"),
            ("Product", "category_name", "product_category_name"),
        ]
        for label, property_name, index_name in index_specs:
            already_exists = any(
                item.get("entityType") == "NODE"
                and item.get("labelsOrTypes") == [label]
                and item.get("properties") == [property_name]
                for item in existing_indexes
            )
            if already_exists:
                continue
            statement = (
                f"CREATE INDEX {index_name} IF NOT EXISTS "
                f"FOR (n:{label}) ON (n.{property_name})"
            )
            self.driver.execute_query(statement, database_=self.settings.neo4j_database)

    def _write_batches(self, statement: str, rows: Iterable[dict]) -> int:
        total = 0
        for batch in _batches(rows):
            self.driver.execute_query(
                statement,
                parameters_={"rows": batch},
                database_=self.settings.neo4j_database,
            )
            total += len(batch)
        return total

    def load_sample(self, data_dir: Path) -> dict[str, int]:
        data_dir = Path(data_dir)
        counts: dict[str, int] = {}
        counts["customers"] = self._write_batches(
            """
            UNWIND $rows AS row
            MERGE (n:Customer {customer_id: row.customer_id})
            SET n.customer_unique_id = row.customer_unique_id,
                n.zip_code_prefix = row.customer_zip_code_prefix,
                n.city = row.customer_city,
                n.state = row.customer_state
            """,
            ({
                "customer_id": r["customer_id"], "customer_unique_id": r["customer_unique_id"],
                "customer_zip_code_prefix": r["customer_zip_code_prefix"], "customer_city": r["customer_city"],
                "customer_state": r["customer_state"],
            } for r in _read_csv(data_dir / "sample_customers.csv")),
        )
        counts["orders"] = self._write_batches(
            """
            UNWIND $rows AS row
            MERGE (n:Order {order_id: row.order_id})
            SET n.status = row.order_status,
                n.purchase_timestamp = row.order_purchase_timestamp,
                n.delivered_customer_date = row.order_delivered_customer_date,
                n.estimated_delivery_date = row.order_estimated_delivery_date
            """,
            ({
                "order_id": r["order_id"], "order_status": r["order_status"],
                "order_purchase_timestamp": r["order_purchase_timestamp"],
                "order_delivered_customer_date": r["order_delivered_customer_date"],
                "order_estimated_delivery_date": r["order_estimated_delivery_date"],
            } for r in _read_csv(data_dir / "sample_orders.csv")),
        )
        counts["products"] = self._write_batches(
            """
            UNWIND $rows AS row
            MERGE (n:Product {product_id: row.product_id})
            SET n.category_name = row.product_category_name,
                n.weight_g = toFloat(row.product_weight_g),
                n.length_cm = toFloat(row.product_length_cm),
                n.height_cm = toFloat(row.product_height_cm),
                n.width_cm = toFloat(row.product_width_cm)
            """,
            ({
                "product_id": r["product_id"], "product_category_name": r["product_category_name"],
                "product_weight_g": r.get("product_weight_g") or None, "product_length_cm": r.get("product_length_cm") or None,
                "product_height_cm": r.get("product_height_cm") or None, "product_width_cm": r.get("product_width_cm") or None,
            } for r in _read_csv(data_dir / "sample_products.csv")),
        )
        counts["sellers"] = self._write_batches(
            """
            UNWIND $rows AS row
            MERGE (n:Seller {seller_id: row.seller_id})
            SET n.state = row.seller_state
            """,
            ({"seller_id": r["seller_id"], "seller_state": r["seller_state"]} for r in self._sample_seller_rows(data_dir)),
        )
        counts["categories"] = self._write_batches(
            """
            UNWIND $rows AS row
            MERGE (n:Category {name: row.name})
            """,
            ({"name": name} for name in self._sample_categories(data_dir)),
        )
        counts["regions"] = self._write_batches(
            """
            UNWIND $rows AS row
            MERGE (n:Region {state: row.state})
            """,
            ({"state": state} for state in self._sample_regions(data_dir)),
        )
        counts["relationships"] = self._load_sample_relationships(data_dir)
        return counts

    @staticmethod
    def _full_seller_states(data_dir: Path) -> dict[str, str | None]:
        """Look up real seller states from the full Olist seller file, if present.

        The reduced four-file sample has no sample_sellers.csv, so without this
        lookup every Seller node would have no state and (Seller)-[:LOCATED_IN]->
        (Region) could never be created.
        """
        full_path = data_dir / "olist_sellers_dataset.csv"
        if not full_path.is_file():
            return {}
        return {row["seller_id"]: row.get("seller_state") or None for row in _read_csv(full_path)}

    @classmethod
    def _sample_seller_rows(cls, data_dir: Path):
        states = cls._full_seller_states(data_dir)
        seen: set[str] = set()
        for row in _read_csv(data_dir / "sample_items.csv"):
            seller_id = row["seller_id"]
            if seller_id not in seen:
                seen.add(seller_id)
                yield {"seller_id": seller_id, "seller_state": states.get(seller_id)}

    @staticmethod
    def _sample_categories(data_dir: Path):
        seen: set[str] = set()
        for row in _read_csv(data_dir / "sample_products.csv"):
            category = row["product_category_name"]
            if category and category not in seen:
                seen.add(category)
                yield category

    @classmethod
    def _sample_regions(cls, data_dir: Path):
        seen: set[str] = set()
        for row in _read_csv(data_dir / "sample_customers.csv"):
            state = row["customer_state"]
            if state and state not in seen:
                seen.add(state)
                yield state
        for state in cls._full_seller_states(data_dir).values():
            if state and state not in seen:
                seen.add(state)
                yield state

    def _load_sample_relationships(self, data_dir: Path) -> int:
        total = 0
        total += self._write_batches(
            """
            UNWIND $rows AS row
            MATCH (c:Customer {customer_id: row.customer_id}), (o:Order {order_id: row.order_id})
            MERGE (c)-[:PLACED]->(o)
            """,
            ({"customer_id": r["customer_id"], "order_id": r["order_id"]} for r in _read_csv(data_dir / "sample_orders.csv")),
        )
        item_rows = list(_read_csv(data_dir / "sample_items.csv"))
        total += self._write_batches(
            """
            UNWIND $rows AS row
            MATCH (o:Order {order_id: row.order_id}), (p:Product {product_id: row.product_id}), (s:Seller {seller_id: row.seller_id})
            MERGE (o)-[r:CONTAINS {item_id: row.order_item_id}]->(p)
            SET r.price = toFloat(row.price), r.freight_value = toFloat(row.freight_value)
            MERGE (o)-[:FULFILLED_BY]->(s)
            """,
            ({"order_id": r["order_id"], "product_id": r["product_id"], "seller_id": r["seller_id"],
              "order_item_id": r["order_item_id"], "price": r["price"], "freight_value": r["freight_value"]} for r in item_rows),
        )
        total += self._write_batches(
            """
            UNWIND $rows AS row
            MATCH (p:Product {product_id: row.product_id}), (c:Category {name: row.category_name})
            MERGE (p)-[:IN_CATEGORY]->(c)
            """,
            ({"product_id": r["product_id"], "category_name": r["product_category_name"]} for r in _read_csv(data_dir / "sample_products.csv")),
        )
        total += self._write_batches(
            """
            UNWIND $rows AS row
            MATCH (c:Customer {customer_id: row.customer_id}), (r:Region {state: row.state})
            MERGE (c)-[:LOCATED_IN]->(r)
            """,
            ({"customer_id": r["customer_id"], "state": r["customer_state"]} for r in _read_csv(data_dir / "sample_customers.csv")),
        )
        seller_states = self._full_seller_states(data_dir)
        # Only seller_ids that actually got a Seller node (i.e. appear in sample_items.csv),
        # so we never MATCH a seller_id with no corresponding node.
        seller_ids_in_sample = {row["seller_id"] for row in self._sample_seller_rows(data_dir)}
        seller_region_rows = [
            {"seller_id": seller_id, "state": seller_states[seller_id]}
            for seller_id in seller_ids_in_sample
            if seller_states.get(seller_id)
        ]
        total += self._write_batches(
            """
            UNWIND $rows AS row
            MATCH (s:Seller {seller_id: row.seller_id}), (r:Region {state: row.state})
            MERGE (s)-[:LOCATED_IN]->(r)
            """,
            iter(seller_region_rows),
        )
        return total

    def run_graph_query(self, statement: str, parameters: dict | None = None) -> tuple[list[dict], float]:
        started = time.perf_counter()
        rows = self.execute_read(statement, parameters)
        return rows, (time.perf_counter() - started) * 1000
