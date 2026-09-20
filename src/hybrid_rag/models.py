from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Engine = Literal["SQL", "GRAPH", "BOTH"]


class RouteDecision(BaseModel):
    engine: Engine
    intent: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class QueryParameter(BaseModel):
    name: str = Field(min_length=1)
    value: str


class QueryPlan(BaseModel):
    engine: Literal["SQL", "GRAPH"]
    statement: str = Field(min_length=1)
    parameters: list[QueryParameter] = Field(default_factory=list)

    def parameter_dict(self) -> dict[str, str]:
        return {parameter.name: parameter.value for parameter in self.parameters}


class ExecutionResult(BaseModel):
    engine: Literal["SQL", "GRAPH"]
    rows: list[dict[str, Any]]
    columns: list[str]
    statement: str
    latency_ms: float = 0


class Answer(BaseModel):
    text: str
    route: Engine
    provenance: list[str] = Field(default_factory=list)
