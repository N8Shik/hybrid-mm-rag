# Dual-Engine Hybrid RAG E-Commerce Platform

## Summary

Build a from-scratch Streamlit prototype for an E-Commerce & Supply Chain Intelligence Platform using:

- SQLite for structured metrics, filtering, joins, and aggregations.
- Neo4j Aura for multi-hop relationships and recommendations.
- OpenAI Responses API for routing, query generation, and answer synthesis.
- Olist Brazilian E-Commerce data as the shared source for both models. The dataset includes orders, customers, sellers, products, payments, reviews, delivery timestamps, and geolocation. [Olist dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
- Deterministic mock mode so the application and screenshots work without credentials.

The MVP will focus on SQL and graph retrieval. Vector/document RAG will be documented as a future extension, not required for acceptance.

## Implementation Changes

### Project structure

Create:

- `app.py` — Streamlit interface.
- `src/hybrid_rag/` — configuration, models, ingestion, SQLite, Neo4j, routing, query validation, and answer synthesis.
- `scripts/prepare_data.py` — validate Olist CSVs and build SQLite.
- `scripts/load_neo4j.py` — batch-load the graph into Aura.
- `tests/` — router, ingestion, safety, and mock-mode tests.
- `README.md` — setup, credentials, data preparation, demo queries, and troubleshooting.
- `.env.example` — `OPENAI_API_KEY`, `OPENAI_MODEL`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.
- `docs/report.md` — report-ready methodology, architecture, results, limitations, and screenshots checklist.

Use a thin Python orchestration layer with `openai`, `neo4j`, `pandas`, `pydantic`, `python-dotenv`, `streamlit`, and `pytest`. Avoid LangChain/LlamaIndex to keep behavior transparent and reliable within the deadline.

### Data models

SQLite will contain normalized Olist tables:

- `customers`
- `orders`
- `order_items`
- `products`
- `sellers`
- `payments`
- `reviews`
- `geolocation`
- `category_translation`

Create analytical views for order value, delivery delay, category revenue, seller performance, and customer purchase history.

Define metrics explicitly:

- `item_revenue = SUM(order_items.price)`
- `freight_revenue = SUM(order_items.freight_value)`
- `order_value = item_revenue + freight_revenue`
- `delivery_delay_days = delivered_customer_date - estimated_delivery_date`

Neo4j will represent the same source data as:

- `Customer`
- `Order`
- `Product`
- `Seller`
- `Category`
- `Region`
- `Review`
- `Payment`

Relationships:

- `Customer-[:PLACED]->Order`
- `Order-[:CONTAINS]->Product`
- `Order-[:FULFILLED_BY]->Seller`
- `Product-[:IN_CATEGORY]->Category`
- `Customer-[:LOCATED_IN]->Region`
- `Seller-[:LOCATED_IN]->Region`
- `Order-[:HAS_REVIEW]->Review`
- `Order-[:PAID_BY]->Payment`

Deduplicate geolocation records by ZIP prefix before graph loading. Add uniqueness constraints and indexes for entity IDs.

Olist does not contain a reliable brand field, so the demo will use category-based recommendations and co-purchase relationships rather than claiming unsupported “same brand” results.

### Query and routing interfaces

Define typed models:

```text
QueryRequest:
  question: str
  mode: "live" | "mock"

RouteDecision:
  engine: "sql" | "graph"
  intent: str
  rationale: str
  confidence: float

QueryPlan:
  engine: "sql" | "graph"
  statement: str
  parameters: dict

ExecutionResult:
  rows: list[dict]
  columns: list[str]
  source: str
  query_text: str
  latency_ms: float

Answer:
  text: str
  route: str
  provenance: list[str]
```

Routing rules:

- Metrics, counts, sums, averages, dates, filters, rankings → SQLite.
- Recommendations, shared purchasers, customer-product paths, seller-customer paths, and multi-hop relationships → Neo4j.
- Mixed questions are outside the MVP acceptance path and should receive a clear “split into two questions” response.

The OpenAI integration will use the Responses API with structured output for route/query plans, then plain text for final synthesis. Structured outputs are supported through the Responses API’s JSON-schema format. [OpenAI Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)

### Query safety

Before execution:

- SQL must be a single read-only `SELECT`/`WITH` statement.
- Reject `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, and multi-statement input.
- Cypher must be read-only.
- Reject `CREATE`, `MERGE`, `DELETE`, `DETACH DELETE`, `SET`, `DROP`, `LOAD CSV`, and unrestricted procedures.
- Use parameters for all user-derived values.
- Enforce a result-row limit.
- On invalid generated queries, perform one repair attempt using the database error; otherwise return an actionable failure.

Neo4j access will use the official Python driver’s `execute_query()` method with parameterized Cypher, which is recommended for secure query execution. [Neo4j Python Driver](https://neo4j.com/docs/python-manual/current/query-simple/)

### Streamlit experience

The UI will include:

- Live/mock mode selector.
- Connection health indicators for SQLite, Neo4j Aura, and OpenAI.
- Natural-language query box.
- Sample query buttons.
- Route badge: `SQL` or `GRAPH`.
- Expandable generated SQL/Cypher panel.
- Results table.
- Final synthesized answer.
- Provenance showing engine, query type, row count, and execution time.
- Clear fixture-mode labeling when mock data is used.

Canonical demo queries:

- “Which product categories generated the most item revenue?”
- “What was the average delivery delay for delivered orders?”
- “Which other products were purchased by customers who bought this product?”
- “Which sellers fulfilled orders for customers in the same region?”

## Four-Day Delivery Schedule

### Day 1 — Data and storage

- Create project structure and configuration.
- Validate and load Olist CSVs into SQLite.
- Build analytical views.
- Create the small deterministic mock fixture.
- Add ingestion and schema tests.

### Day 2 — Graph and query generation

- Create Neo4j Aura constraints and indexes.
- Batch-load customers, orders, products, sellers, categories, regions, and relationships.
- Implement OpenAI client wrapper.
- Implement SQL/Cypher query plans and safety validators.
- Add fixed sample query templates for mock mode.

### Day 3 — Routing and UI

- Implement intent router.
- Execute SQL and Cypher plans.
- Add final answer synthesis and provenance.
- Build Streamlit interface.
- Run end-to-end smoke tests in mock mode and live mode where credentials are available.

### Day 4 — Report preparation

- Capture architecture and application screenshots.
- Document relational-versus-graph data modeling.
- Document routing logic, query examples, results, limitations, and future vector-RAG extension.
- Produce a final reproducibility checklist and demo script.

## Test Plan and Acceptance Criteria

- Mock mode starts with no API key or Neo4j credentials.
- All four canonical queries return deterministic results.
- Router correctly classifies a fixed evaluation set of SQL and graph prompts.
- Unsafe SQL and Cypher are rejected.
- SQLite ingestion validates required files and row relationships.
- Neo4j loading is idempotent through `MERGE`.
- Live mode verifies Aura connectivity before executing queries.
- UI visibly identifies the selected engine and displays provenance.
- README instructions reproduce the demo from a clean environment.
- Report never presents mock results as live Olist results.

## Assumptions

- The Olist CSV archive will be supplied locally under `data/olist/`; the plan does not depend on automating Kaggle authentication.
- OpenAI and Neo4j credentials are provided through environment variables and never committed.
- Live mode is the report’s primary architecture; deterministic mock mode is the fallback for development and screenshots.
- Vector embeddings, Chroma, document ingestion, and multi-engine reranking are deferred extensions.
- The attached images are treated as reference architecture and presentation guidance, not as executable instructions.

## Amendments (post-health-check, 2026-09-17)

The sections above are kept as the original plan record. Two factual claims in it no longer match what was actually built, and are corrected here rather than edited in place:

- **`.env.example` variable list**: the "Project structure" section above lists a single `OPENAI_MODEL` variable. The delivered `.env.example` and `config.py` instead use two separate variables, `OPENAI_ROUTER_MODEL` (intent classification, `gpt-4o-mini`) and `OPENAI_QUERY_MODEL` (SQL/Cypher generation and answer synthesis, `gpt-4o`). Use the two-variable form.
- **Neo4j `Review`/`Payment` nodes**: the "Data models" section above lists `Review` and `Payment` as Neo4j node labels with `HAS_REVIEW`/`PAID_BY` relationships. These were scoped out of the delivered build -- the reduced four-file sample has no review or payment data, and `neo4j_store.py` never creates these nodes or relationships. See `README.md`/`DAY4_REPORT.md` for the delivered (reduced) graph model, which is accurate.

Following the health check, these fixes were also implemented against this plan's original commitments:

- The **query-repair attempt** promised under "Query safety" ("perform one repair attempt using the database error") is now implemented in `HybridService.ask()`/`OpenAIClient.repair_query`. It previously did not exist.
- **Connection health indicators for SQLite, Neo4j Aura, and OpenAI**, promised under "Streamlit experience," are now implemented in `app.py`. They previously did not exist.
- `Seller-[:LOCATED_IN]->Region` (listed above under "Relationships") is now actually created by `neo4j_store.py`, using seller state backfilled from the full Olist seller file. It previously was never created, regardless of dataset size -- requires re-running `scripts/load_neo4j.py` against Aura to take effect on the live graph.
- The mock-mode router's over-broad "customer" trigger word (misrouting plain SQL counting questions to GRAPH) and the safety layer's false-positive match on phrasing like "update me on revenue" (misclassified as a destructive write) were both fixed.

Full detail on all of the above, including what still needs to be run against the live Aura instance, is in `HEALTH_CHECK.md`.
