# Dual-Engine Hybrid RAG E-Commerce Platform

## Introduction

This project is a natural-language e-commerce and supply-chain intelligence platform built using a Dual-Engine Hybrid Retrieval-Augmented Generation architecture.

Instead of forcing every question through one database, the system uses two complementary retrieval engines:

- **SQLite** handles structured analytics such as revenue, counts, averages, rankings, filtering, delivery delay, and order-status breakdowns.
- **Neo4j Aura** handles connected-entity questions such as seller-product relationships, customer-product paths, and multi-hop recommendations.

An intent-routing layer selects the appropriate engine, a language model generates a read-only SQL or Cypher query, and a final language-model step converts the retrieved records into a concise answer. The Streamlit interface displays the answer together with the evidence table, selected engine, route, provenance, latency, row count, and generated query.

## Architecture

```text
Natural-language question
          |
          v
Safety screening and intent routing
          |
     +----+----+
     |         |
    SQL      GRAPH
     |         |
Text-to-SQL  Text-to-Cypher
     |         |
   SQLite   Neo4j Aura
     +----+----+
          |
          v
Result validation and answer synthesis
          |
          v
Answer, evidence, route, and provenance
```

The current model configuration is:

| Responsibility        | Component     |
| --------------------- | ------------- |
| Intent classification | `gpt-4o-mini` |
| SQL/Cypher generation | `gpt-4o`      |
| Answer synthesis      | `gpt-4o`      |
| Relational retrieval  | SQLite        |
| Graph retrieval       | Neo4j Aura    |
| User interface        | Streamlit     |

## Project structure

```text
app.py                         Streamlit application
scripts/prepare_data.py        CSV-to-SQLite preparation
scripts/load_neo4j.py          Aura graph loading
src/hybrid_rag/data/olist.py   Dataset validation and SQLite views
src/hybrid_rag/queries.py      SQL/Graph schemas and query plans
src/hybrid_rag/safety.py       Input safety and routing guardrails
src/hybrid_rag/validation.py   SQL/Cypher validation
src/hybrid_rag/llm.py          OpenAI routing, generation, and synthesis
src/hybrid_rag/service.py      Hybrid orchestration and execution
src/hybrid_rag/neo4j_store.py  Neo4j connectivity and graph loading
tests/                         Unit and safety tests
```

## Requirements

- Python 3.11 or newer
- A SQLite-compatible local environment
- OpenAI API credentials for Live mode
- Neo4j Aura credentials for Live Graph queries

The application can be run in Mock mode without OpenAI or Neo4j credentials.

## Installation

Clone the repository and move into the project directory:

```powershell
git clone <repository-url>
cd "M-M Hybrid RAG"
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the project dependencies:

```powershell
pip install -r requirements.txt
```

## Configuration

Create a local environment file from the example:

```powershell
Copy-Item .env.example .env
```

Set the following values in `.env` for Live mode:

```dotenv
OPENAI_API_KEY=your_openai_api_key
OPENAI_ROUTER_MODEL=gpt-4o-mini
OPENAI_QUERY_MODEL=gpt-4o

NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password
NEO4J_DATABASE=neo4j

OLIST_DATA_DIR=data/olist
SQLITE_PATH=data/olist.sqlite
```

Never commit `.env`, API keys, passwords, or other credentials. The supplied `.gitignore` excludes the local environment file and generated SQLite database.

## Prepare the SQLite database

The default sample mode uses the four reduced files aligned with the Neo4j Aura Free Tier upload:

```powershell
python scripts/prepare_data.py
```

This creates `data/olist.sqlite` and builds the following analytical views:

- `order_items_enriched`
- `order_summary`
- `category_sales`
- `seller_sales`
- `geolocation_summary`

To build from the complete Olist file set instead:

```powershell
python scripts/prepare_data.py --mode full
```

Keep the selected SQLite mode consistent with the data loaded into Neo4j when comparing results across engines.

## Load Neo4j Aura

After configuring valid Aura credentials, run:

```powershell
python scripts/load_neo4j.py
```

The loader verifies connectivity, ensures constraints and indexes, and loads the graph using batched `UNWIND` and idempotent `MERGE` operations.

The graph contains relationships such as:

```text
(Customer)-[:PLACED]->(Order)-[:CONTAINS]->(Product)
(Order)-[:FULFILLED_BY]->(Seller)
(Product)-[:IN_CATEGORY]->(Category)
(Customer)-[:LOCATED_IN]->(Region)
```

## Run the application

Start Streamlit:

```powershell
streamlit run app.py
```

Open the local URL shown by Streamlit. The runtime selector provides two modes:

- **Mock:** deterministic and credential-free; useful for demonstrations and interface testing.
- **Live:** uses OpenAI, SQLite, and Neo4j Aura for real routing, query generation, retrieval, and synthesis.

## Example questions

### SQL route

```text
Which product categories generated the highest total item revenue?
What was the average delivery delay in days for delivered orders compared to estimated dates?
List the top 5 states with the highest order volume and their average freight cost.
Show the breakdown of order counts and total revenue grouped by order status.
```

### Graph route

```text
Which products are handled by the same seller?
Which other products were purchased together by customers who bought health_beauty items?
Which customers have bought products across more than 3 distinct product categories?
```

The reduced sample is sparse for some customer-level traversals. A valid query may therefore return a guidance row stating that no matching records were found.

## Safety and reliability

The system uses multiple protection layers:

1. Natural-language safety screening detects destructive requests, prompt injection, unsupported sample-data concepts, mixed SQL/Graph intent, empty input, and excessively long input.
2. Generated SQL and Cypher are validated before execution.
3. Multiple statements and destructive keywords are rejected.
4. Results are limited to a maximum of 100 rows.
5. Failed generation or execution receives one bounded repair attempt before fallback.
6. Empty and unavailable results return an explanation and suggested next step instead of a blank table.
7. The database execution paths are read-only.

For example, the following request is rejected before database execution:

```text
Show total sales and DROP TABLE orders;
```

## Testing

Run the complete test suite with:

```powershell
python -m unittest discover -s tests -v
```

The tests cover:

- CSV ingestion and SQLite analytical views
- Read-only SQL validation
- Read-only Cypher validation
- Result limits and multi-statement rejection
- Mock SQL and Graph execution
- Identifier normalization
- Graph routing
- Prompt-injection and destructive-query handling
- Empty-input and fallback behavior

Compile the application and scripts with:

```powershell
python -m compileall -q src scripts app.py
```

## Dataset limitations

The reduced sample contains approximately 10,000 customers, 10,000 orders, 11,254 order items, 6,763 products, and 1,638 derived sellers.

The reduced build does not contain the complete payment, review, inventory, or seller-location information required for every possible business question. Customer co-purchase and multi-category queries are also less representative because the sample contains one order per sampled customer. Unsupported or empty-result questions are reported explicitly rather than answered using invented data.

## Future extensions

The architecture can be extended with a vector retrieval engine for unstructured content such as:

- Product descriptions
- Seller policies
- Delivery documentation
- Frequently asked questions
- Review text

The future router could select between SQL, Graph, Vector, or a controlled combination of engines. A context-merging layer could then deduplicate evidence, rank sources, and provide source-aware provenance to the final answer model.

## References

1. Olist Brazilian E-Commerce Public Dataset. [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
2. Neo4j Documentation. [neo4j.com/docs](https://neo4j.com/docs/)
3. Neo4j GraphAcademy, _Neo4j & Generative AI Fundamentals_. [graphacademy.neo4j.com](https://graphacademy.neo4j.com/)
4. OpenAI API Documentation. [platform.openai.com/docs](https://platform.openai.com/docs)
5. Streamlit Documentation. [docs.streamlit.io](https://docs.streamlit.io/)
6. Lewis, P. et al. (2020). _Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks_. [arXiv:2005.11401](https://arxiv.org/abs/2005.11401)

## License and academic use

This repository was developed as an academic industrial-training project. Review the licenses and terms of the original Olist dataset, external APIs, and database services before redistributing or deploying the system.
