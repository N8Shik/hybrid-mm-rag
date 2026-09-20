from __future__ import annotations

import json
from typing import TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from .config import Settings
from .models import QueryPlan, RouteDecision
from .queries import GRAPH_SCHEMA, SQL_SCHEMA


ModelT = TypeVar("ModelT", bound=BaseModel)


def _strict_schema(schema: dict) -> dict:
    """Make Pydantic's JSON schema compatible with strict Structured Outputs."""
    if isinstance(schema, dict):
        if schema.get("type") == "object" or "properties" in schema:
            schema["additionalProperties"] = False
            properties = schema.get("properties", {})
            if properties:
                schema["required"] = list(properties)
        for value in schema.values():
            if isinstance(value, (dict, list)):
                _strict_schema(value) if isinstance(value, dict) else [_strict_schema(item) for item in value if isinstance(item, dict)]
    elif isinstance(schema, list):
        for item in schema:
            _strict_schema(item)
    return schema


class OpenAIClient:
    def __init__(self, settings: Settings | None = None):
        load_dotenv()
        self.settings = settings or Settings.from_environment()
        if not self.settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for live LLM mode")
        if not self.settings.openai_router_model or not self.settings.openai_query_model:
            raise ValueError("OPENAI_ROUTER_MODEL and OPENAI_QUERY_MODEL are required")
        self.client = OpenAI(api_key=self.settings.openai_api_key)

    def _structured(self, model: str, instructions: str, output_type: type[ModelT]) -> ModelT:
        schema = _strict_schema(output_type.model_json_schema())
        response = self.client.responses.create(
            model=model,
            instructions=instructions,
            input="Return only the requested structured result.",
            text={
                "format": {
                    "type": "json_schema",
                    "name": output_type.__name__.lower(),
                    "schema": schema,
                    "strict": True,
                }
            },
            store=False,
        )
        return output_type.model_validate(json.loads(response.output_text))

    def route(self, question: str) -> RouteDecision:
        instructions = f"""
Classify this e-commerce analytics question into exactly one engine: SQL, GRAPH, or BOTH.
SQL handles metrics, aggregations, filtering, rankings, dates, and numeric facts.
GRAPH handles recommendations, shared customers/products, paths, and multi-hop relationships.
BOTH is only for a question that explicitly requires independent SQL metrics and graph relationships.
Question: {question}
""".strip()
        return self._structured(self.settings.openai_router_model, instructions, RouteDecision)

    def generate_query(self, question: str, engine: str) -> QueryPlan:
        schema_name = "SQL" if engine.upper() == "SQL" else "GRAPH"
        schema = SQL_SCHEMA if schema_name == "SQL" else GRAPH_SCHEMA
        instructions = f"""
Generate one safe, read-only {schema_name} query for the user's e-commerce question.
Use only the supplied schema. Never invent tables, labels, properties, or relationships.
If the requested field or relationship is absent from the schema, do not guess or fabricate it.
Return parameters separately; never concatenate user values into the query.
Do not write data or call procedures. Include a result LIMIT of at most 100.
Schema:
{schema}
Question: {question}
""".strip()
        return self._structured(self.settings.openai_query_model, instructions, QueryPlan)

    def repair_query(self, question: str, engine: str, failed_statement: str, error_message: str) -> QueryPlan:
        """One repair attempt: ask the model to fix a query using the database/validation error.

        Implements the PLAN.md query-safety requirement: "On invalid generated queries,
        perform one repair attempt using the database error; otherwise return an actionable
        failure." Callers get exactly one shot at this before falling back.
        """
        schema_name = "SQL" if engine.upper() == "SQL" else "GRAPH"
        schema = SQL_SCHEMA if schema_name == "SQL" else GRAPH_SCHEMA
        instructions = f"""
The previous {schema_name} query you generated for this question failed validation or execution.
Fix it. Use only the supplied schema. Never invent tables, labels, properties, or relationships.
Return parameters separately; never concatenate user values into the query.
Do not write data or call procedures. Include a result LIMIT of at most 100.
Schema:
{schema}
Question: {question}
Previous statement:
{failed_statement}
Error:
{error_message}
""".strip()
        return self._structured(self.settings.openai_query_model, instructions, QueryPlan)

    def synthesize(self, question: str, results: str) -> str:
        response = self.client.responses.create(
            model=self.settings.openai_query_model,
            instructions="Answer using only the supplied database results. Be concise and mention when no result is available.",
            input=f"Question: {question}\nDatabase results:\n{results}",
            store=False,
        )
        return response.output_text.strip()
