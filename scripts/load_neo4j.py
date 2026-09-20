from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402
from neo4j.exceptions import AuthError  # noqa: E402

from hybrid_rag.config import Settings  # noqa: E402
from hybrid_rag.neo4j_store import Neo4jStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the reduced Olist graph into Neo4j Aura.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "olist")
    args = parser.parse_args()
    load_dotenv()
    store = Neo4jStore(Settings.from_environment())
    try:
        try:
            store.verify_connectivity()
        except AuthError as error:
            raise SystemExit(
                "Neo4j authentication failed. Reset/copy the Aura password from the Connect panel, "
                "then rerun this command. No graph data was written."
            ) from error
        print("Neo4j connectivity verified")
        store.ensure_schema()
        print("Neo4j constraints and indexes ensured")
        counts = store.load_sample(args.data_dir)
        for name, count in counts.items():
            print(f"{name}: {count:,}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
