from __future__ import annotations

import html
import sqlite3
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from hybrid_rag.config import Settings  # noqa: E402
from hybrid_rag.neo4j_store import Neo4jStore  # noqa: E402
from hybrid_rag.service import HybridService, QueryResponse  # noqa: E402


st.set_page_config(page_title="Engine Lens", page_icon="◇", layout="wide", initial_sidebar_state="collapsed")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
        :root { --ink: #e8eef8; --muted: #a9b6ca; --line: #27364a; --panel: #151f2c; --panel-2: #1a2635; --cyan: #25d7f7; --violet: #ad82ff; --green: #37e695; }
        .stApp { background: #0c131d; color: var(--ink); font-family: 'DM Sans', sans-serif; }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stToolbar"] { visibility: hidden; }
        .block-container { max-width: 1440px; padding: 1.2rem 2.8rem 3rem; }
        .topbar { display:flex; align-items:center; justify-content:space-between; padding: .25rem 0 1.15rem; border-bottom: 1px solid #1c2a3a; margin-bottom: 2.8rem; }
        .brand { display:flex; align-items:center; gap:.75rem; font-size:1.1rem; font-weight:700; letter-spacing:-.02em; }
        .brand-mark { color: var(--cyan); font-size:1.65rem; line-height:1; }
        .tagline { color:var(--muted); font-size:.9rem; margin-left:1rem; padding-left:1rem; border-left:1px solid #304054; }
        .workspace { color:var(--muted); font-size:.85rem; }
        .hero { text-align:center; padding-bottom:1.4rem; }
        .hero h1 { font-size:2.85rem; line-height:1.1; letter-spacing:-.06em; margin:.1rem 0 .35rem; color:#f2f6fc; }
        .hero p { color:#aebed3; font-size:1.05rem; margin:0; }
        .query-help { color:#8494aa; font-size:.78rem; text-align:center; margin-top:.25rem; }
        .answer-heading { font-size:1.45rem; font-weight:700; margin:1.5rem 0 1rem; }
        .answer-lead { font-size:1.45rem; line-height:1.42; color:#f1f5fb; margin-bottom:.35rem; }
        .answer-body { color:#b8c5d7; font-size:1rem; line-height:1.5; margin-bottom:1.35rem; }
        .table-title { font-size:1.05rem; font-weight:600; border-top:1px solid var(--line); padding-top:1rem; margin-top:1.1rem; }
        .inspector { border-left:1px solid #304054; padding-left:2rem; }
        .inspector h2 { font-size:1.25rem; margin:1.55rem 0 1.45rem; }
        .inspector-label { color:#f1f5fb; font-size:.86rem; font-weight:600; margin:1.2rem 0 .5rem; }
        .inspector-sub { color:#91a2b8; font-size:.78rem; line-height:1.45; }
        .engine-row { display:flex; align-items:center; gap:.55rem; }
        .engine-icon { width:2.35rem; height:2.35rem; border-radius:50%; background:#192637; display:flex; align-items:center; justify-content:center; color:var(--cyan); font-size:1.15rem; }
        .engine-name { font-weight:600; }
        .route { display:flex; align-items:center; gap:.35rem; margin:.65rem 0 .35rem; }
        .route-pill { flex:1; border:1px solid; border-radius:2rem; padding:.55rem .7rem; text-align:center; font-size:.83rem; font-weight:600; }
        .route-sql { border-color:var(--cyan); color:var(--cyan); }
        .route-graph { border-color:var(--violet); color:var(--violet); }
        .route-inactive { opacity:.34; }
        .route-active { box-shadow:0 0 0 1px currentColor inset; }
        .route-line { width:1.15rem; height:2px; background:linear-gradient(90deg,var(--cyan),var(--violet)); }
        .inspector-divider { height:1px; background:var(--line); margin:1.4rem 0; }
        .stat-row { display:flex; gap:1.1rem; }
        .stat { flex:1; }
        .stat-value { color:#f1f5fb; font-size:1.1rem; font-weight:600; }
        .stat-label { color:#8393aa; font-size:.73rem; margin-top:.15rem; }
        .takeaway { border:1px solid #274253; border-left:3px solid var(--cyan); background:#111f2c; border-radius:.45rem; padding:1rem 1.15rem; margin-top:1.4rem; }
        .takeaway-title { color:var(--cyan); font-weight:700; margin-bottom:.35rem; }
        .takeaway-copy { color:#b8c5d7; font-size:.9rem; line-height:1.45; }
        div[data-testid="stTextArea"] textarea { background:#151f2c; border:1px solid #3a4c64; color:#ecf3fb; border-radius:.65rem; font-size:1.05rem; padding:1rem; }
        div[data-testid="stTextArea"] textarea:focus { border-color:var(--cyan); box-shadow:0 0 0 1px var(--cyan); }
        div.stButton > button, div.stFormSubmitButton > button { background:#21cfee; color:#07121c; border:0; border-radius:2rem; font-weight:700; min-height:2.5rem; }
        div.stButton > button:hover, div.stFormSubmitButton > button:hover { background:#56e3f7; color:#07121c; }
        div[data-testid="stDataFrame"] { border:1px solid #2b3b50; border-radius:.45rem; overflow:hidden; }
        details { border-color:#2b3b50 !important; }
        .mode-chip { color:#8fa0b5; font-size:.78rem; text-align:right; margin-top:-2.2rem; margin-bottom:1.5rem; }
        .health-row { display:flex; gap:.7rem; justify-content:center; flex-wrap:wrap; margin-bottom:1.3rem; }
        .health-pill { display:flex; align-items:center; gap:.4rem; font-size:.76rem; color:var(--muted); background:#131e2b; border:1px solid #253547; border-radius:1.2rem; padding:.35rem .75rem; }
        .health-dot { width:.5rem; height:.5rem; border-radius:50%; flex-shrink:0; }
        .health-ok { background:var(--green); }
        .health-error { background:#ff6b6b; }
        .health-unconfigured { background:#5b6b80; }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=30, show_spinner=False)
def check_connections(
    sqlite_path: str,
    neo4j_uri: str | None,
    neo4j_username: str | None,
    neo4j_password: str | None,
    has_openai_key: bool,
    check_live: bool,
) -> dict[str, tuple[str, str]]:
    """Connection-health indicators for SQLite, Neo4j Aura, and OpenAI (PLAN.md, Streamlit experience).

    SQLite is always checked (local, no network, no credentials). Neo4j/OpenAI are only
    probed in live mode, so mock mode stays fully credential-free as documented.
    """
    statuses: dict[str, tuple[str, str]] = {}
    try:
        uri = f"file:{sqlite_path}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("SELECT 1")
        connection.close()
        statuses["SQLite"] = ("ok", "Reachable")
    except Exception as error:
        statuses["SQLite"] = ("error", str(error)[:120])

    if not check_live:
        statuses["Neo4j Aura"] = ("unconfigured", "Not checked in mock mode")
        statuses["OpenAI"] = ("unconfigured", "Not checked in mock mode")
        return statuses

    if neo4j_uri and neo4j_username and neo4j_password:
        try:
            store = Neo4jStore(Settings(neo4j_uri=neo4j_uri, neo4j_username=neo4j_username, neo4j_password=neo4j_password))
            try:
                store.verify_connectivity()
                statuses["Neo4j Aura"] = ("ok", "Reachable")
            finally:
                store.close()
        except Exception as error:
            statuses["Neo4j Aura"] = ("error", str(error)[:120])
    else:
        statuses["Neo4j Aura"] = ("unconfigured", "Credentials not set")

    statuses["OpenAI"] = ("ok", "API key configured") if has_openai_key else ("unconfigured", "API key not set")
    return statuses


def render_connection_health(statuses: dict[str, tuple[str, str]]) -> None:
    dot_class = {"ok": "health-ok", "error": "health-error", "unconfigured": "health-unconfigured"}
    pills = "".join(
        f"<div class='health-pill'><span class='health-dot {dot_class.get(state, 'health-unconfigured')}'></span>{html.escape(name)}: {html.escape(detail)}</div>"
        for name, (state, detail) in statuses.items()
    )
    st.markdown(f"<div class='health-row'>{pills}</div>", unsafe_allow_html=True)


def render_header(mode: str) -> None:
    st.markdown(
        f"<div class='topbar'><div class='brand'><span class='brand-mark'>✦</span><span>Engine Lens</span><span class='tagline'>Ask. Retrieve. Understand. Drive.</span></div><div class='workspace'>E-commerce Intelligence &nbsp; <span style='color:#37e695'>●</span> {mode.title()}</div></div>",
        unsafe_allow_html=True,
    )


def render_inspector(response: QueryResponse) -> None:
    st.markdown("<div class='inspector'><h2>Contextual Inspector</h2>", unsafe_allow_html=True)
    st.markdown("<div class='inspector-label'>Selected Engine</div>", unsafe_allow_html=True)
    icon = "▣" if response.engine_name == "SQLite" else ("⌘" if response.engine_name == "Neo4j" else "✓")
    st.markdown(f"<div class='engine-row'><div class='engine-icon'>{icon}</div><div><div class='engine-name'>E-commerce Data</div><div class='inspector-sub'>{response.engine_name} · orders, items, customers, sellers</div></div></div>", unsafe_allow_html=True)
    st.markdown("<div class='inspector-label'>Query Route</div>", unsafe_allow_html=True)
    route_description = {"SQL": "structured analytics", "GRAPH": "relationship traversal", "SAFETY": "safety fallback"}.get(response.route, "query planning")
    sql_state = "route-active" if response.route == "SQL" else "route-inactive"
    graph_state = "route-active" if response.route == "GRAPH" else "route-inactive"
    st.markdown(f"<div class='route'><div class='route-pill route-sql {sql_state}'>▤ &nbsp;SQL</div><div class='route-line'></div><div class='route-pill route-graph {graph_state}'>⌘ &nbsp;Graph</div></div><div class='inspector-sub'>Routed to {response.route} · {route_description}</div>", unsafe_allow_html=True)
    st.markdown("<div class='inspector-label'>Data Provenance</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='engine-row'><div class='engine-icon'>▧</div><div><div class='engine-name'>sample Olist dataset</div><div class='inspector-sub'>{html.escape(response.provenance)}</div></div></div>", unsafe_allow_html=True)
    st.markdown("<div class='inspector-divider'></div><div class='inspector-label'>Latency & Rows</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='stat-row'><div class='stat'><div class='stat-value'>{response.latency_ms/1000:.1f}s</div><div class='stat-label'>Latency</div></div><div class='stat'><div class='stat-value'>{len(response.rows)}</div><div class='stat-label'>Rows returned</div></div></div>", unsafe_allow_html=True)
    st.markdown("<div class='inspector-divider'></div>", unsafe_allow_html=True)
    with st.expander("Generated Query"):
        st.code(response.statement, language="sql" if response.route == "SQL" else "cypher" if response.route == "GRAPH" else "text")
    st.markdown("</div>", unsafe_allow_html=True)


def render_response(response: QueryResponse) -> None:
    left, right = st.columns([3.35, 1.35], gap="large")
    with left:
        is_safety = response.route == "SAFETY"
        evidence_title = "Guidance" if is_safety else "Evidence"
        evidence_copy = "No database query was executed. The guidance below explains the safe next step." if is_safety else "The result is grounded in the selected retrieval engine. The evidence below is a compact, readable view of the returned records."
        st.markdown("<div class='answer-heading'>Answer</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='answer-lead'>{html.escape(response.answer)}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='answer-body'>{html.escape(evidence_copy)}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='table-title'>{evidence_title}</div>", unsafe_allow_html=True)
        st.dataframe(response.rows[:10], use_container_width=True, hide_index=True, height=245)
        takeaway = "No data or schema was changed. Rephrase the request using the suggested next step." if is_safety else "The answer is grounded in a read-only query, with the route and provenance visible alongside the result."
        st.markdown(f"<div class='takeaway'><div class='takeaway-title'>Key takeaway</div><div class='takeaway-copy'>{takeaway}</div></div>", unsafe_allow_html=True)
    with right:
        render_inspector(response)


def main() -> None:
    inject_styles()
    settings = Settings.from_environment()
    mode = st.session_state.get("mode", "mock")
    mode_col, _ = st.columns([1, 5])
    with mode_col:
        mode = st.selectbox("Runtime", ["mock", "live"], index=0 if mode == "mock" else 1, label_visibility="collapsed")
    st.session_state.mode = mode
    render_header(mode)
    statuses = check_connections(
        str(settings.sqlite_path),
        settings.neo4j_uri,
        settings.neo4j_username,
        settings.neo4j_password,
        bool(settings.openai_api_key),
        mode == "live",
    )
    render_connection_health(statuses)
    st.markdown("<div class='hero'><h1>Ask your commerce data anything.</h1><p>Natural language. Real data. Deeper insights.</p></div>", unsafe_allow_html=True)

    with st.form("query_form", clear_on_submit=False):
        question = st.text_area("Query", value=st.session_state.get("question", "Which product categories generated the most item revenue?"), label_visibility="collapsed", height=80)
        submitted = st.form_submit_button("Ask  →", use_container_width=False)
    st.markdown("<div class='query-help'>Try: &nbsp; “Top categories by revenue” &nbsp;&nbsp;&nbsp; “What was the average delivery delay?” &nbsp;&nbsp;&nbsp; “Show products handled by the same seller”</div>", unsafe_allow_html=True)
    mode_copy = "Mock is deterministic and credential-free." if mode == "mock" else "Live uses OpenAI, SQLite, and Neo4j Aura."
    st.markdown(f"<div class='mode-chip'>Mode: <b>{mode.title()}</b> · {mode_copy}</div>", unsafe_allow_html=True)

    cols = st.columns(3)
    examples = ["Which product categories generated the most item revenue?", "What was the average delivery delay?", "Which products are handled by the same seller?"]
    for col, example in zip(cols, examples):
        with col:
            if st.button(example, key=f"example_{example}", use_container_width=True):
                st.session_state.question = example
                st.rerun()

    if submitted:
        st.session_state.question = question
        try:
            response = HybridService(settings, mode=mode).ask(question)
            st.session_state.response = response
        except Exception as error:
            st.session_state.pop("response", None)
            st.error(str(error))

    response = st.session_state.get("response")
    if response:
        render_response(response)
    else:
        st.markdown("<div style='height:12rem'></div>", unsafe_allow_html=True)
        st.markdown("<div style='text-align:center;color:#71839a'>Ask a question to see the answer, route, and evidence.</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
