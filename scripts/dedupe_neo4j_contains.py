from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from hybrid_rag.config import Settings  # noqa: E402
from hybrid_rag.neo4j_store import Neo4jStore  # noqa: E402


DESCRIPTION = """
Clean up legacy duplicate (Order)-[:CONTAINS]->(Product) relationships in Aura.

Background: the current loader (neo4j_store.py) keys each CONTAINS relationship on an
`item_id` property so reruns MERGE cleanly. If an earlier version of the loader (or a
manual import) ever wrote CONTAINS edges without that property, those older edges are
never matched by later MERGEs and pile up alongside the correctly-keyed ones -- this is
almost certainly the "duplicate CONTAINS relationships" noted in DAY4_REPORT.md's
limitations section.

Policy: for every (Order, Product) pair that has more than one CONTAINS relationship, if
at least one of them has item_id set, this script deletes the ones that are missing
item_id (the legacy leftovers) and keeps the properly-keyed ones. Pairs where NONE of the
relationships have item_id are left untouched and only reported, since there is no way to
tell a genuine duplicate apart from two legitimate line items without that key.

Always run with --dry-run first (the default) to see counts before deleting anything.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=DESCRIPTION.strip())
    parser.add_argument("--apply", action="store_true", help="Actually delete the legacy duplicate relationships. Without this flag, only reports what would be deleted.")
    args = parser.parse_args()

    load_dotenv()
    store = Neo4jStore(Settings.from_environment())
    try:
        store.verify_connectivity()
        print("Neo4j connectivity verified")

        with store.driver.session(database=store.settings.neo4j_database) as session:
            summary = session.run(
                """
                MATCH (o:Order)-[r:CONTAINS]->(p:Product)
                WITH o, p, count(r) AS relCount, count(CASE WHEN r.item_id IS NOT NULL THEN 1 END) AS keyedCount
                WHERE relCount > 1
                RETURN
                    count(*) AS pairsWithMultipleContains,
                    sum(relCount) AS totalRelsInThosePairs,
                    sum(CASE WHEN keyedCount > 0 THEN relCount - keyedCount ELSE 0 END) AS legacyRelsToDelete,
                    sum(CASE WHEN keyedCount = 0 THEN relCount ELSE 0 END) AS unresolvableRels
                """
            ).single()
            print("Diagnostic summary:", dict(summary) if summary else None)

            if not args.apply:
                print()
                print("Dry run only - no relationships were deleted. Re-run with --apply to delete the legacy (item_id IS NULL) duplicates.")
                return

            deleted = session.run(
                """
                MATCH (o:Order)-[r:CONTAINS]->(p:Product)
                WITH o, p, collect(r) AS rels
                WHERE size(rels) > 1 AND any(rel IN rels WHERE rel.item_id IS NOT NULL)
                UNWIND rels AS rel
                WITH rel WHERE rel.item_id IS NULL
                DELETE rel
                RETURN count(rel) AS deletedCount
                """
            ).single()
            print("Deleted legacy CONTAINS relationships:", dict(deleted) if deleted else None)
    finally:
        store.close()


if __name__ == "__main__":
    main()
