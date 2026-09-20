from __future__ import annotations

import re

from .models import QueryPlan


MAX_RESULT_ROWS = 100

_SQL_FORBIDDEN = re.compile(
    r"\b(?:insert|update|delete|drop|alter|attach|detach|replace|vacuum|reindex|pragma|create)\b",
    re.IGNORECASE,
)
_CYPHER_FORBIDDEN = re.compile(
    r"\b(?:create|merge|delete|detach\s+delete|set|remove|drop|load\s+csv|call|apoc)\b",
    re.IGNORECASE,
)


def _single_statement(statement: str) -> str:
    cleaned = statement.strip()
    if not cleaned:
        raise ValueError("Query is empty")
    if ";" in cleaned.rstrip(";"):
        raise ValueError("Multiple statements are not allowed")
    return cleaned.rstrip(";").strip()


def validate_sql(statement: str) -> str:
    cleaned = _single_statement(statement)
    if not re.match(r"^(?:select|with)\b", cleaned, re.IGNORECASE):
        raise ValueError("Only read-only SELECT or WITH SQL is allowed")
    if _SQL_FORBIDDEN.search(cleaned):
        raise ValueError("SQL contains a forbidden write or administrative operation")
    return cleaned


def validate_cypher(statement: str) -> str:
    cleaned = _single_statement(statement)
    if not re.match(r"^(?:match|optional\s+match|unwind)\b", cleaned, re.IGNORECASE):
        raise ValueError("Only read-only MATCH or UNWIND Cypher is allowed")
    if _CYPHER_FORBIDDEN.search(cleaned):
        raise ValueError("Cypher contains a forbidden write or procedure operation")
    return cleaned


def with_result_limit(statement: str, engine: str, limit: int = MAX_RESULT_ROWS) -> str:
    if limit < 1 or limit > MAX_RESULT_ROWS:
        raise ValueError(f"limit must be between 1 and {MAX_RESULT_ROWS}")
    validator = validate_sql if engine.upper() == "SQL" else validate_cypher
    cleaned = validator(statement)
    if not re.search(r"\blimit\s+\d+\b", cleaned, re.IGNORECASE):
        cleaned = f"{cleaned}\nLIMIT {limit}"
    return cleaned


def validate_plan(plan: QueryPlan) -> QueryPlan:
    statement = with_result_limit(plan.statement, plan.engine)
    return plan.model_copy(update={"statement": statement})

