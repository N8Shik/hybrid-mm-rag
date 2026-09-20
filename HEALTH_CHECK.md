# Health Check — Dual-Engine Hybrid RAG (2026-09-17)

Scope: read every file in `src/hybrid_rag/`, `app.py`, `scripts/`, `tests/`, config files, and cross-checked behavior against `PLAN.md`, `README.md`, and `DAY4_REPORT.md`. Ran the full unit test suite (15/15 pass). Independently queried the live `data/olist.sqlite` on-device, and separately recomputed metrics against the full 99,441-row original Olist CSVs to check the shrunk sample for bias. **Follow-up: every fixable item below was then implemented directly in the project and verified.** See "Resolution" under each item.

## Confirmed accurate (no issue)
- Dataset row counts in `DAY4_REPORT.md` §7 match `data/olist.sqlite` exactly, before and after the fixes below.
- Safety/validation layer correctly blocks the destructive-SQL, injection, and split-question demo cases in the report's demo script; all 15 unit tests pass throughout.
- **The average delivery delay of −11.14 days is not a sampling artifact and is not wrong.** Full dataset = −11.88 days, a true random 10,000-order sample = −11.99 days, the shrunk sample on a calendar-day basis = −11.84 days — all consistent. 91.9% of orders arrive before their estimated delivery date; this is a documented Olist characteristic, not a bug. The small gap between −11.14 (the app's fractional julianday calc) and −11.84 (calendar-day) comes from `order_estimated_delivery_date` having no time component while `order_delivered_customer_date` does (~16:47 average) — a property of the source data, not the pipeline.

## Inconsistencies and gaps found — now resolved

1. **No query-repair fallback, despite the plan promising one.**
   **Resolution: implemented.** Added `OpenAIClient.repair_query()` (`llm.py`) and wired one repair attempt into `HybridService.ask()` (`service.py`): on a validation or execution failure, the failed statement + error is sent back to the model once before falling back. Verified with a scripted fake-LLM test exercising both the "repair succeeds" and "repair also fails" paths.

2. **UI missing the planned connection-health indicators.**
   **Resolution: implemented.** Added `check_connections()` (cached 30s) and `render_connection_health()` to `app.py`, showing SQLite/Neo4j Aura/OpenAI status pills. SQLite is always checked locally; Neo4j/OpenAI are only probed in live mode so mock mode stays credential-free. Syntax-verified (`py_compile`); not run end-to-end since Streamlit isn't installed in this sandbox — worth a quick `streamlit run app.py` check on your side.

3. **Mock-mode router misclassified plain counting questions as GRAPH.**
   **Resolution: implemented.** Removed the bare "customer" trigger word from `HybridService._mock_route`. Reproduced before/after: "How many customers are there in the sample?" now correctly routes to SQL/SQLite; "Which products are handled by the same seller?" still correctly routes to GRAPH/Neo4j.

4. **Safety layer false-positive on "update me on...".**
   **Resolution: implemented.** Tightened `_WRITE_REQUEST` in `safety.py` from `update\s+\w+` to `update\s+\w+\s+set`. Verified "Can you update me on total revenue by category?" now passes safety, while "Update orders set order_status = 'shipped'" and the DROP TABLE demo case are still correctly blocked.

5. **Seller state/region data structurally absent (always NULL).**
   **Resolution: implemented.** `data/olist.py`'s `_derive_sample_sellers` now backfills `seller_zip_code_prefix`/`seller_city`/`seller_state` from the full `olist_sellers_dataset.csv` (present alongside the sample files) when available. Rebuilt `data/olist.sqlite`: all 1,638 sellers now have a real state; `seller_sales` breaks out across 22 distinct states. Verified the untouched metrics (delivery delay, category revenue, all row counts) are unchanged after the rebuild.

6. **Seller↔Region graph relationship permanently absent.**
   **Resolution: implemented in code, not yet applied to live Aura.** `neo4j_store.py` now sets a `state` property on `Seller` nodes and creates `(Seller)-[:LOCATED_IN]->(Region)`, using the same seller-state backfill as #5; `_sample_regions` now also includes seller-only states so no `Region` node is missing. `queries.py`'s `GRAPH_SCHEMA` updated to state this plainly instead of "optionally." Verified the pure-Python data-prep logic directly (all 1,638 sellers resolve a state; all 1,638 edges would be created; no missing Region node) — **could not run this against your live Aura instance from this sandbox (network egress blocked, same as the original health check). You'll need to re-run `python scripts/load_neo4j.py` yourself; it's MERGE-based, so it's safe to rerun and won't duplicate existing data.**

7. **`PLAN.md` stale relative to what was built.**
   **Resolution: implemented.** Added an "Amendments (post-health-check)" section to the end of `PLAN.md` correcting the `OPENAI_MODEL` vs. `OPENAI_ROUTER_MODEL`/`OPENAI_QUERY_MODEL` claim and the `Review`/`Payment` graph-node claim, and logging the fixes made in this pass — without rewriting the original plan's history.

8. **Day 3 tests not hermetic.**
   **Resolution: implemented.** `tests/test_day3_service.py` now builds its own temp SQLite from the committed sample CSVs via `build_sqlite()` in `setUp`/`tearDown`, instead of depending on a pre-built `data/olist.sqlite`. Verified by moving `data/olist.sqlite` out of the way entirely and re-running the suite — still 15/15.

9. **Duplicate `CONTAINS` relationships (legacy import artifact).**
   **Resolution: tooling added, not yet applied to live Aura.** Added `scripts/dedupe_neo4j_contains.py`: reports (and, with `--apply`, deletes) legacy `CONTAINS` edges that are missing the `item_id` key where a properly-keyed edge already exists for the same order/product pair, leaving genuinely ambiguous pairs untouched. **Cannot run this against your Aura instance from this sandbox — run it yourself, with `--apply` only after reviewing the dry-run counts.**

10. **Sample-generation notebook used `head(10000)`, not an explicit random sample.**
    **Resolution: implemented, deliberately scoped.** `data/olist/cleaner.ipynb` now uses `df_orders.sample(n=10000, random_state=42)` instead of `.head(10000)`. **Did not regenerate the already-shipped `sample_*.csv` files, `data/olist.sqlite`, or the Aura graph** — doing so would shift the specific numbers already baked into `DAY4_REPORT.md` (category rankings, delay figure, etc.) and would need you to redo the Aura load. This is a forward-looking fix for reproducibility, not a retroactive one.

## Verification performed (this pass)
- Full unit test suite: 15/15 pass, both with and without a pre-existing `data/olist.sqlite`.
- Direct before/after reproduction of the mock-router and safety false-positive fixes.
- A scripted fake-LLM test exercising the new repair-attempt path (success and double-failure cases).
- Rebuilt `data/olist.sqlite` and confirmed seller state is populated across all 1,638 sellers with no drift in previously-reported metrics.
- Verified the Neo4j loader's new seller/region logic in pure Python (CSV join, edge construction) without touching Aura — live application still needs to happen on your end via `scripts/load_neo4j.py`.
- `py_compile` on every changed Python file plus JSON-validated the edited notebook.

## Still needs your action
- Run `python scripts/load_neo4j.py` against your Aura instance to apply the new Seller state/region data (#6).
- Run `python scripts/dedupe_neo4j_contains.py` (dry run first, then `--apply`) to clean up the legacy duplicate `CONTAINS` edges (#9).
- Optionally open `streamlit run app.py` to eyeball the new connection-health pills (#2) — not exercised end-to-end from this sandbox.
- Decide whether to actually regenerate `sample_*.csv`/`olist.sqlite`/the Aura graph from the notebook's new random sample, and refresh `DAY4_REPORT.md`'s numbers if so (#10) — left as-is for now since it would invalidate currently-reported figures.
