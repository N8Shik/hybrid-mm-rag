# Dual-Engine Hybrid RAG E-Commerce Platform

Day 1 currently provides the data and storage foundation for the summer-training prototype. The default runtime uses the reduced four-file sample because it matches the dataset uploaded to Neo4j Aura Free Tier:

- Olist CSV validation and ingestion
- SQLite relational tables and analytical views
- A deterministic mini-fixture for offline tests
- Reproducible configuration through `.env.example`

## Prepare the reduced SQLite database

The expected source directory is `data/olist/` and must contain `sample_customers.csv`, `sample_orders.csv`, `sample_items.csv`, and `sample_products.csv`.

```powershell
python scripts/prepare_data.py
```

This creates `data/olist.sqlite`. The generated database is ignored by Git and can be rebuilt at any time.

The sample mode loads exactly those four files. Seller IDs are derived from `sample_items.csv`; unavailable payments, reviews, geolocation, and category translations remain empty. To rebuild against the complete nine-file Olist dataset instead, run:

```powershell
python scripts/prepare_data.py --mode full
```

## Run Day 1 tests

```powershell
python -m unittest discover -s tests -v
```

The tests validate the real dataset file set and the deterministic fixture, including the analytical views.

## SQLite views

- `order_items_enriched` — item facts joined to orders, products, translated categories, and sellers
- `order_summary` — order-level item revenue, freight, order value, and delivery delay
- `category_sales` — category-level order count and revenue
- `seller_sales` — seller/state-level order count and revenue
- `geolocation_summary` — one averaged location row per ZIP prefix

## Configuration

Copy `.env.example` to `.env` when configuring the later OpenAI and Neo4j stages. `OLIST_DATA_MODE=sample` keeps SQLite aligned with the reduced Aura graph; use `full` only when loading the complete dataset into both engines.

## Day 2: load the sample graph

After setting valid Aura credentials in `.env`, run:

```powershell
python scripts/load_neo4j.py
```

The loader verifies connectivity, creates idempotent constraints/indexes, and batch-loads the four sample files. It uses `MERGE`, so rerunning it does not intentionally duplicate nodes or relationships.

The OpenAI wrapper uses `OPENAI_ROUTER_MODEL` for intent classification and `OPENAI_QUERY_MODEL` for SQL/Cypher generation. It requests strict JSON Schema output and keeps API response storage disabled.

The reduced sample contains one order per sampled customer, so customer co-purchase recommendations are not representative. The graph demo therefore uses the valid multi-hop path `Product → Order → Seller → Order → Product` for same-seller recommendations.

## Day 3: run the Engine Lens UI

Start the minimal Streamlit interface with:

```powershell
streamlit run app.py
```

The default `mock` runtime is deterministic and works without credentials. Switch the runtime selector to `live` after configuring `.env` to route questions through `gpt-4o-mini`, generate SQL/Cypher with `gpt-4o`, execute against SQLite or Aura, and synthesize a grounded answer. Each response exposes its result table, route, provenance, latency, row count, and generated read-only query.

## Live-mode safety and fallbacks

Before calling an LLM or either database, Engine Lens rejects destructive write requests, prompt-injection wording, unsupported sample-data concepts (inventory, payments, and reviews), and mixed metric-plus-recommendation requests. The UI presents a safe explanation and next step instead of a blank table.

Generated SQL and Cypher are validated again before execution. Empty, invalid, or unavailable results return a visible guidance row; no fallback attempts to write data or invent missing fields. The reduced sample does not include reviews, payments, inventory, seller-region links, or customers with more than three categories, so those requests are expected to return guidance rather than fabricated results.

## Day 4: report package

The report-ready documentation is in [DAY4_REPORT.md](DAY4_REPORT.md). It includes the architecture, relational-versus-graph data models, routing and safety logic, tested SQL/Graph examples, application screenshots, limitations, the planned vector-RAG extension, reproducibility checklist, and presentation demo script. Supporting screenshots and documentation are in [docs](docs/).
