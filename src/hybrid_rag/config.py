from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

try:
    import streamlit as _st  # type: ignore
except ImportError:  # pragma: no cover - streamlit not installed (plain scripts/tests)
    _st = None  # type: ignore


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    olist_data_dir: Path = ROOT_DIR / "data" / "olist"
    sqlite_path: Path = ROOT_DIR / "data" / "olist.sqlite"
    dataset_mode: str = "sample"
    openai_api_key: str | None = None
    openai_router_model: str | None = None
    openai_query_model: str | None = None
    neo4j_uri: str | None = None
    neo4j_username: str | None = None
    neo4j_password: str | None = None
    neo4j_database: str = "neo4j"

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        # On Streamlit Community Cloud there is no .env file; secrets are set via
        # the app's "Secrets" panel and exposed through st.secrets, not os.environ.
        # Bridge them into os.environ so the lookups below keep working unchanged.
        if _st is not None:
            try:
                for key, value in _st.secrets.items():
                    os.environ.setdefault(key, str(value))
            except Exception:
                pass
        return cls(
            olist_data_dir=Path(os.getenv("OLIST_DATA_DIR", ROOT_DIR / "data" / "olist")),
            sqlite_path=Path(os.getenv("SQLITE_PATH", ROOT_DIR / "data" / "olist.sqlite")),
            dataset_mode=os.getenv("OLIST_DATA_MODE", "sample"),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_router_model=os.getenv("OPENAI_ROUTER_MODEL", "gpt-4o-mini") or None,
            openai_query_model=os.getenv("OPENAI_QUERY_MODEL", "gpt-4o") or None,
            neo4j_uri=os.getenv("NEO4J_URI") or None,
            neo4j_username=os.getenv("NEO4J_USERNAME") or None,
            neo4j_password=os.getenv("NEO4J_PASSWORD") or None,
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
        )
