from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.hybrid_rag.data.olist import TABLE_FILES, build_sqlite, validate_dataset


ROOT = Path(__file__).resolve().parents[1]
REAL_DATA = ROOT / "data" / "olist"
FIXTURE_DATA = ROOT / "tests" / "fixtures" / "olist_mini"


class OlistIngestionTests(unittest.TestCase):
    def test_real_dataset_has_all_expected_files(self):
        counts = validate_dataset(REAL_DATA, "full")
        self.assertEqual(set(counts), set(TABLE_FILES))
        self.assertGreater(counts["orders"], 90_000)
        self.assertGreater(counts["order_items"], 90_000)

    def test_fixture_builds_views_and_indexes(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fixture.sqlite"
            counts = build_sqlite(FIXTURE_DATA, database)
            self.assertEqual(counts["orders"], 3)
            connection = sqlite3.connect(database)
            try:
                views = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='view'")}
                self.assertTrue({"order_summary", "category_sales", "seller_sales", "geolocation_summary"} <= views)
                order_value = connection.execute("SELECT order_value FROM order_summary WHERE order_id='order-1'").fetchone()[0]
                self.assertAlmostEqual(order_value, 113.29)
                top_category = connection.execute("SELECT category_name FROM category_sales ORDER BY item_revenue DESC LIMIT 1").fetchone()[0]
                self.assertEqual(top_category, "electronics")
            finally:
                connection.close()

    def test_sample_mode_loads_only_the_four_reduced_files(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "sample.sqlite"
            counts = build_sqlite(REAL_DATA, database, "sample")
            self.assertEqual(counts["customers"], 10_000)
            self.assertEqual(counts["orders"], 10_000)
            self.assertEqual(counts["order_items"], 11_254)
            self.assertEqual(counts["products"], 6_763)
            self.assertGreater(counts["sellers"], 0)
            self.assertEqual(counts["payments"], 0)
            self.assertEqual(counts["reviews"], 0)
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM order_summary").fetchone()[0], 10_000)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM geolocation").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM category_translation").fetchone()[0], 0)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
