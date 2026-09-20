from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyDecision:
    kind: str
    message: str
    suggestion: str


_WRITE_REQUEST = re.compile(
    r"\b(?:drop\s+(?:table|database)|delete\s+from|truncate|alter\s+table|insert\s+into|update\s+\w+\s+set|create\s+table|load\s+csv)\b",
    re.IGNORECASE,
)
_PROMPT_INJECTION = re.compile(
    r"\b(?:ignore\s+(?:all|any|previous)|system\s+prompt|developer\s+message|reveal\s+(?:the\s+)?(?:prompt|instructions))\b",
    re.IGNORECASE,
)
_UNAVAILABLE_CONCEPTS = {
    "inventory": "Stock and inventory quantities are not included in this Olist sample.",
    "stock quantity": "Stock and inventory quantities are not included in this Olist sample.",
    "quantity remaining": "Stock and inventory quantities are not included in this Olist sample.",
    "warehouse stock": "Warehouse inventory is not included in this Olist sample.",
    "review": "Review and star-rating data were not loaded into the reduced four-file sample.",
    "rating": "Review and star-rating data were not loaded into the reduced four-file sample.",
    "5-star": "Review and star-rating data were not loaded into the reduced four-file sample.",
    "payment method": "Payment data were not loaded into the reduced four-file sample.",
}
_SQL_SIGNALS = ("total revenue", "revenue", "average", "highest", "lowest", "top ", "order volume", "order count", "freight", "breakdown", "grouped")
_GRAPH_SIGNALS = ("recommend", "purchased together", "same order", "same seller", "network", "path", "relationship", "connected", "who bought", "customers who", "other products")


def assess_question(question: str) -> SafetyDecision | None:
    normalized = " ".join(question.split())
    lowered = normalized.lower()
    if not normalized:
        return SafetyDecision("empty", "Enter a question to query the commerce data.", "Try a revenue metric or a customer–product relationship question.")
    if len(normalized) > 1_000:
        return SafetyDecision("too_long", "This question is too long to evaluate safely.", "Keep the request under 1,000 characters and ask one analytical question at a time.")
    if _WRITE_REQUEST.search(normalized):
        return SafetyDecision("unsafe", "No database command was run because the request includes a destructive write operation.", "Ask for a read-only metric, filter, ranking, or relationship traversal instead.")
    if _PROMPT_INJECTION.search(normalized):
        return SafetyDecision("injection", "I can only process a read-only e-commerce analytics question.", "Ask about the available orders, products, customers, sellers, revenue, freight, delivery, or graph relationships.")
    for phrase, message in _UNAVAILABLE_CONCEPTS.items():
        if phrase in lowered:
            return SafetyDecision("unavailable", message, "Try revenue, order status, delivery delay, state-level freight, seller links, or product-category relationships.")
    has_sql = any(signal in lowered for signal in _SQL_SIGNALS)
    has_graph = any(signal in lowered for signal in _GRAPH_SIGNALS)
    if has_sql and has_graph:
        return SafetyDecision("mixed", "This combines a numerical metric with a recommendation or relationship traversal.", "Split it into two questions: first the metric, then the relationship or recommendation question.")
    return None


def requires_graph_traversal(question: str) -> bool:
    """Recognize relationship questions whose wording also contains counts or thresholds."""
    lowered = question.lower()
    entity_count = sum(entity in lowered for entity in ("customer", "seller", "order", "product", "categor"))
    relational_language = any(phrase in lowered for phrase in ("fulfilled", "bought", "purchased", "same region", "same state", "across", "together", "connected"))
    return entity_count >= 2 and relational_language
