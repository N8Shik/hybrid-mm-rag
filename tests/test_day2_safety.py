from __future__ import annotations

import unittest

from src.hybrid_rag.models import QueryPlan
from src.hybrid_rag.queries import MOCK_GRAPH_PLANS, MOCK_SQL_PLANS
from src.hybrid_rag.validation import validate_cypher, validate_sql, validate_plan


class Day2SafetyTests(unittest.TestCase):
    def test_read_only_sql_is_accepted_and_limited(self):
        plan = validate_plan(QueryPlan(engine="SQL", statement="SELECT * FROM category_sales"))
        self.assertIn("LIMIT 100", plan.statement)

    def test_write_sql_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_sql("DELETE FROM orders")

    def test_read_only_cypher_is_accepted(self):
        query = validate_cypher("MATCH (p:Product) RETURN p.product_id LIMIT 5")
        self.assertIn("MATCH", query)

    def test_write_cypher_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_cypher("MATCH (p:Product) SET p.flag = true RETURN p")

    def test_mock_templates_exist_for_both_engines(self):
        self.assertIn("top_categories", MOCK_SQL_PLANS)
        self.assertIn("co_purchased_products", MOCK_GRAPH_PLANS)
        self.assertEqual(MOCK_GRAPH_PLANS["co_purchased_products"].engine, "GRAPH")

    def test_query_parameters_are_typed(self):
        self.assertEqual(MOCK_GRAPH_PLANS["co_purchased_products"].parameter_dict(), {})


if __name__ == "__main__":
    unittest.main()
