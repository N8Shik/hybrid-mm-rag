from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .llm import OpenAIClient
from .models import ExecutionResult, QueryPlan, RouteDecision
from .neo4j_store import Neo4jStore
from .queries import MOCK_GRAPH_PLANS, MOCK_SQL_PLANS
from .safety import SafetyDecision, assess_question, requires_graph_traversal
from .validation import validate_plan


MOCK_GRAPH_ROWS = [
    {"product_id": "35afc973633aaeb6b877ff57b2793310", "category_name": "casa_conforto", "same_seller_count": 18},
    {"product_id": "84f456958365164420cfc80fbe4c7fab", "category_name": "cama_mesa_banho", "same_seller_count": 15},
    {"product_id": "777d2e438a1b645f3aec9bd57e92672c", "category_name": "cama_mesa_banho", "same_seller_count": 12},
    {"product_id": "422879e10f46682990de24d770e7f83d", "category_name": "ferramentas_jardim", "same_seller_count": 9},
    {"product_id": "aca2eb7d00ea1a7b8ebd4e68314663af", "category_name": "moveis_decoracao", "same_seller_count": 8},
]


@dataclass
class QueryResponse:
    question: str
    route: str
    engine_name: str
    answer: str
    rows: list[dict]
    columns: list[str]
    statement: str
    latency_ms: float
    provenance: str
    mode: str


class SQLiteExecutor:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def execute(self, plan: QueryPlan) -> ExecutionResult:
        plan = validate_plan(plan)
        started = time.perf_counter()
        uri = f"file:{self.database_path.resolve()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.execute(plan.statement, plan.parameter_dict())
            rows = [dict(row) for row in cursor.fetchall()]
            columns = [description[0] for description in cursor.description or []]
        finally:
            connection.close()
        return ExecutionResult(
            engine="SQL",
            rows=rows,
            columns=columns,
            statement=plan.statement,
            latency_ms=(time.perf_counter() - started) * 1000,
        )


class HybridService:
    def __init__(self, settings: Settings | None = None, mode: str = "mock"):
        self.settings = settings or Settings.from_environment()
        self.mode = mode
        self.sqlite = SQLiteExecutor(self.settings.sqlite_path)
        self._llm: OpenAIClient | None = None
        self._neo4j: Neo4jStore | None = None

    @property
    def llm(self) -> OpenAIClient:
        if self._llm is None:
            self._llm = OpenAIClient(self.settings)
        return self._llm

    @property
    def neo4j(self) -> Neo4jStore:
        if self._neo4j is None:
            self._neo4j = Neo4jStore(self.settings)
        return self._neo4j

    def close(self) -> None:
        if self._neo4j is not None:
            self._neo4j.close()

    @staticmethod
    def _fallback_response(question: str, decision: SafetyDecision, statement: str = "-- No database query was executed.") -> QueryResponse:
        return QueryResponse(
            question=question,
            route="SAFETY",
            engine_name="Query Safety",
            answer=decision.message,
            rows=[{"Status": "Needs adjustment", "Suggested next step": decision.suggestion}],
            columns=["Status", "Suggested next step"],
            statement=statement,
            latency_ms=0,
            provenance="Safety guardrail · no data was changed",
            mode="safe",
        )

    @staticmethod
    def _empty_result_response(question: str, route: str, engine_name: str, statement: str, latency_ms: float) -> QueryResponse:
        suggestion = "Try fewer filters, a broader date range, or one of the available product categories."
        return QueryResponse(
            question=question,
            route=route,
            engine_name=engine_name,
            answer="The query ran safely, but no matching records were found in the loaded sample.",
            rows=[{"Status": "No matching records", "Suggested next step": suggestion}],
            columns=["Status", "Suggested next step"],
            statement=statement,
            latency_ms=latency_ms,
            provenance=f"{engine_name} read-only query · live data",
            mode="live",
        )

    @staticmethod
    def _query_context(question: str) -> str:
        """Add only verified vocabulary hints for translated sample-category names."""
        aliases = {
            "health_beauty": "beleza_saude",
            "health and beauty": "beleza_saude",
            "health & beauty": "beleza_saude",
        }
        lowered = question.lower()
        hints = [f'Use category value "{target}" for the user term "{source}".' for source, target in aliases.items() if source in lowered]
        return question if not hints else f"{question}\n\nDataset vocabulary note: {' '.join(hints)}"

    @staticmethod
    def _display_key(key: str) -> str:
        labels = {
            "seller_id": "Seller",
            "product_id": "Product",
            "product_ids": "Products",
            "customer_id": "Customer",
            "order_id": "Order",
            "category_name": "Category",
            "same_seller_count": "Related Products",
        }
        if key in labels:
            return labels[key]
        normalized_key = key.lower().replace(".", "_").replace(" ", "_")
        if "product" in normalized_key and normalized_key.endswith("ids"):
            return "Products"
        if "product" in normalized_key and normalized_key.endswith("id"):
            return "Product"
        if "seller" in normalized_key and normalized_key.endswith("id"):
            return "Seller"
        return key.replace("_", " ").title()

    @classmethod
    def _friendly_id(cls, key: str, value: str, row: dict) -> str:
        if not isinstance(value, str) or len(value) < 12:
            return value
        if not re.fullmatch(r"[0-9a-fA-F-]+", value):
            return value
        normalized_key = key.lower().replace(".", "_").replace(" ", "_")
        entity_key = normalized_key.removesuffix("_ids").removesuffix("_id")
        if "product" in normalized_key:
            entity = "Product"
        elif "seller" in normalized_key:
            entity = "Seller"
        elif "customer" in normalized_key:
            entity = "Customer"
        elif "order" in normalized_key:
            entity = "Order"
        else:
            entity = entity_key.replace("_", " ").title()
        short_id = value[:8].lower()
        category = row.get("category_name") if entity == "Product" else None
        if category:
            return f"{entity} · {category} · {short_id}"
        return f"{entity} · {short_id}"

    @classmethod
    def _normalize_rows(cls, rows: list[dict]) -> list[dict]:
        normalized = []
        for row in rows:
            display_row = {}
            for key, value in row.items():
                display_key = cls._display_key(key)
                if isinstance(value, list):
                    value = [cls._friendly_id(key, item, row) for item in value]
                else:
                    value = cls._friendly_id(key, value, row)
                display_row[display_key] = value
            normalized.append(display_row)
        return normalized

    @classmethod
    def _normalize_answer(cls, answer: str, rows: list[dict], question: str = "") -> str:
        replacements = {}
        for row in rows:
            for key, value in row.items():
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if isinstance(item, str) and len(item) >= 12:
                        replacements[item] = cls._friendly_id(key, item, row)
        question_ids = re.findall(r"[0-9a-fA-F]{32}", question)
        for raw_id in question_ids:
            if raw_id not in replacements:
                key = "product_id" if "product" in question.lower() else "record_id"
                replacements[raw_id] = cls._friendly_id(key, raw_id, {})
        for raw_id in re.findall(r"[0-9a-fA-F]{32}", answer):
            if raw_id not in replacements:
                key = "product_id" if "product" in question.lower() else "record_id"
                replacements[raw_id] = cls._friendly_id(key, raw_id, {})
        for raw_id, friendly_id in sorted(replacements.items(), key=lambda pair: len(pair[0]), reverse=True):
            answer = answer.replace(raw_id, friendly_id)
        return answer

    @staticmethod
    def _mock_route(question: str) -> RouteDecision:
        lower = question.lower()
        # Deliberately excludes bare entity words like "customer" or "seller": those
        # appear in plain SQL aggregation questions too (e.g. "how many customers are
        # there?") and previously caused mock mode to misroute them to GRAPH.
        graph_words = ("recommend", "same seller", "same-seller", "bought", "purchased", "path", "relationship", "co-purchase", "who bought", "also bought")
        if any(word in lower for word in graph_words):
            return RouteDecision(engine="GRAPH", intent="relationship traversal", rationale="The question asks about connected entities or recommendations.", confidence=1.0)
        return RouteDecision(engine="SQL", intent="structured analytics", rationale="The question asks for a metric, ranking, filter, or aggregation.", confidence=1.0)

    def _mock_response(self, question: str, route: RouteDecision) -> QueryResponse:
        if route.engine == "SQL":
            if "delay" in question.lower():
                plan = MOCK_SQL_PLANS["delivery_delay"]
            else:
                plan = MOCK_SQL_PLANS["top_categories"]
            result = self.sqlite.execute(plan)
            if result.rows and "category_name" in result.rows[0]:
                top = result.rows[0]
                answer = f"{top['category_name']} generated the highest item revenue at ${top['item_revenue']:,.2f}. The table below shows the leading categories in the sample."
                columns = ["#", "Product Category", "Item Revenue", "Order Count", "Freight Revenue"]
                rows = [
                    {"#": index, "Product Category": row["category_name"], "Item Revenue": f"${row['item_revenue']:,.2f}", "Order Count": f"{row['order_count']:,}", "Freight Revenue": f"${row['freight_revenue']:,.2f}"}
                    for index, row in enumerate(result.rows[:5], 1)
                ]
            else:
                value = result.rows[0].get("average_delivery_delay_days") if result.rows else None
                answer = f"The average delivery delay in the sample is {value} days." if value is not None else "No delivery-delay records were available."
                columns = ["Metric", "Value"]
                rows = [{"Metric": "Average delivery delay (days)", "Value": value}]
            return QueryResponse(question, "SQL", "SQLite", answer, rows, columns, result.statement, result.latency_ms, "SQLite analytical views · sample Olist data", "mock")

        plan = MOCK_GRAPH_PLANS["co_purchased_products"]
        plan = plan.model_copy(update={"parameters": []})
        return QueryResponse(question, "GRAPH", "Neo4j", "These products are connected through shared sellers with the selected product. The graph path makes the recommendation relationship explicit.", self._normalize_rows(MOCK_GRAPH_ROWS), ["Product", "Category", "Related Products"], plan.statement, 42.0, "Neo4j relationship traversal · sample Olist graph", "mock")

    def _execute_plan(self, plan: QueryPlan) -> tuple[ExecutionResult, str]:
        if plan.engine == "SQL":
            return self.sqlite.execute(plan), "SQLite"
        started = time.perf_counter()
        rows = self.neo4j.execute_read(plan.statement, plan.parameter_dict())
        result = ExecutionResult(
            engine="GRAPH",
            rows=rows,
            columns=list(rows[0].keys()) if rows else [],
            statement=plan.statement,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        return result, "Neo4j"

    def _attempt_repair(self, question: str, engine: str, failed_statement: str, error_message: str):
        """One repair attempt using the database/validation error, per PLAN.md.

        Returns (plan, result, engine_name) on success, or None if the repair also fails.
        """
        try:
            repaired_plan = validate_plan(self.llm.repair_query(question, engine, failed_statement, error_message))
            result, engine_name = self._execute_plan(repaired_plan)
            return repaired_plan, result, engine_name
        except Exception:
            return None

    def ask(self, question: str) -> QueryResponse:
        safety = assess_question(question)
        if safety:
            return self._fallback_response(question, safety)
        try:
            if requires_graph_traversal(question):
                route = RouteDecision(engine="GRAPH", intent="multi-hop relationship traversal", rationale="The question connects multiple commerce entities through relationships.", confidence=1.0)
            else:
                route = self._mock_route(question) if self.mode == "mock" else self.llm.route(question)
        except Exception:
            return self._fallback_response(question, SafetyDecision("service", "The query service could not classify this request right now.", "Check the live credentials and try again with a shorter, single-engine question."))
        if self.mode == "mock":
            return self._mock_response(question, route)
        if route.engine == "BOTH":
            return self._fallback_response(question, SafetyDecision("mixed", "This combines SQL analytics and graph traversal in one request.", "Split it into one metric question and one relationship question so each engine can return reliable evidence."))
        query_context = self._query_context(question)
        failed_statement = "-- no statement generated --"
        try:
            raw_plan = self.llm.generate_query(query_context, route.engine)
            failed_statement = raw_plan.statement
            plan = validate_plan(raw_plan)
            result, engine_name = self._execute_plan(plan)
        except ValueError as error:
            repaired = self._attempt_repair(query_context, route.engine, failed_statement, str(error))
            if repaired is None:
                return self._fallback_response(question, SafetyDecision("validation", "The generated query was rejected before execution, and one repair attempt using the validation error also failed to produce a safe query.", "Try a simpler question using orders, products, customers, sellers, revenue, freight, delivery, or product categories."), "-- Query rejected by safety validation.")
            plan, result, engine_name = repaired
        except Exception as error:
            repaired = self._attempt_repair(query_context, route.engine, failed_statement, str(error))
            if repaired is None:
                return self._fallback_response(question, SafetyDecision("execution", "The requested data could not be retrieved from the selected engine, even after one repair attempt using the database error.", "Try a simpler wording or a different available field; no data was changed."))
            plan, result, engine_name = repaired
        if not result.rows:
            return self._empty_result_response(question, route.engine, engine_name, result.statement, result.latency_ms)
        try:
            answer = self.llm.synthesize(question, json.dumps(result.rows, default=str))
        except Exception:
            answer = "The query completed successfully. Review the evidence table for the returned records."
        return QueryResponse(
            question,
            route.engine,
            engine_name,
            self._normalize_answer(answer, result.rows, question),
            self._normalize_rows(result.rows),
            [self._display_key(column) for column in result.columns],
            result.statement,
            result.latency_ms,
            f"{engine_name} read-only query · live data",
            "live",
        )
