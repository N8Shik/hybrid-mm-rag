from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hybrid_rag.data.olist import TABLE_FILES, build_sqlite, validate_dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Olist CSV files into SQLite.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "olist")
    parser.add_argument("--sqlite-path", type=Path, default=ROOT / "data" / "olist.sqlite")
    parser.add_argument("--mode", choices=("sample", "full"), default="sample")
    args = parser.parse_args()
    validate_dataset(args.data_dir, args.mode)
    loaded = build_sqlite(args.data_dir, args.sqlite_path, args.mode)
    print(f"SQLite database created at {args.sqlite_path}")
    for table in TABLE_FILES:
        print(f"{table}: {loaded[table]:,} rows")


if __name__ == "__main__":
    main()
