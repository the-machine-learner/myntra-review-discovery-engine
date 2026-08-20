"""Streamlit dashboard — Myntra Wishlist Discovery Engine.

MVP: 2 of 5 planned screens (Opportunity Scorecard, Live Chat). Deep-Dive,
Wishlist Segments, and Review Explorer are designed into data_loader.py's
schema but not built yet (see plan-3.md Track B).
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import altair as alt
import pandas as pd
import streamlit as st

from src.config import get_secret
from src.dashboard.bootstrap import apply_streamlit_secrets
from src.dashboard.constants import APP_TITLE, APP_SUBTITLE
from src.dashboard.data_loader import load_dashboard_data
from src.dashboard.style import (
    inject_global_css,
    esc,
    format_chat_answer,
    render_html,
    stars,
    MYNTRA_ORANGE,
    MYNTRA_PURPLE,
)
from src.rag.pipeline import answer_question
from src.rag.retriever import ReviewRetriever
from src.analysis import budget as groq_budget

apply_streamlit_secrets(st)
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

_AXIS = alt.Axis(
    labelColor="#B6ABB6",
    titleColor="#FFFFFF",
    gridColor="#2A1840",
    tickColor="#351F50",
    labelLimit=1000,
    labelFontSize=11,
)

_FEASIBILITY_COLORS = {"yes": "#2ECC71", "partial": "#F2C744", "no": "#FF6B6B"}


@st.cache_resource(show_spinner="Connecting to vector search index...")
def _get_retriever() -> ReviewRetriever:
    return ReviewRetriever()


@st.cache_data(show_spinner="Loading opportunity-analysis artifacts...")
def _load_data():
    return load_dashboard_data()


def render_header(data) -> None:
    render_html(
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;'
        f'flex-wrap:wrap;gap:1rem;margin-bottom:1.4rem;">'
        f'<div><div style="font-size:1.6rem;font-weight:900;color:#FFFFFF;letter-spacing:-.02em;">'
        f'🛍️ {esc(APP_TITLE)}</div>'
        f'<div style="color:#B6ABB6;font-size:.92rem;margin-top:.2rem;">{esc(APP_SUBTITLE)}</div></div>'
        f'</div>'
    )
    meta = data.opportunity_run_metadata
    if not meta:
        render_html(
            '<div class="rd-card" style="border-left:3px solid #F2C744;">'
            '<b style="color:#F2C744;">No analysis run yet.</b> '
            '<span style="color:#B6ABB6;">Showing the ingested corpus only. Run '
            '<code>python -m src.analysis.run</code> to populate the Opportunity Scorecard.</span>'
            '</div>'
        )
    else:
        cols = st.columns(4)
        cols[0].metric("Corpus size", f"{meta.get('corpus_size_at_run', len(data.reviews)):,}")
        cols[1].metric("Areas analyzed", len(meta.get("area_ids", [])))
        cols[2].metric("Groq calls (last run)", meta.get("groq_call_count", 0))
        cols[3].metric("Validation OK", "✅" if meta.get("validation_ok", True) else "⚠️")


def render_opportunity_scorecard(data) -> None:
    render_html(
        '<div class="rd-section-title">Opportunity Scorecard</div>'
        '<div class="rd-section-sub">Reach × Impact, sized by confidence, colored by whether a '
        'non-monetary lever exists — this is the "quantify and compare" view.</div>'
    )

    if not data.opportunities:
        render_html(
            '<div class="rd-card">No opportunity scores yet. Run '
            '<code>python -m src.analysis.run</code> (rule-only: add <code>--skip-llm</code> '
            'for a free dry run) to populate this screen.</div>'
        )
        return

    rows = []
    for op in data.opportunities:
        rows.append(
            {
                "Opportunity": op["label"],
                "area_id": op["area_id"],
                "Reach %": op["reach"]["pct"],
                "Impact": op["impact"]["blended_impact_score"],
                "Confidence": op["confidence"]["confidence_score"],
                "Signal Score": op["signal_score"],
                "Feasible w/o $": op["feasible_without_monetary_incentive"],
                "Matched reviews": op["reach"]["matched_count"],
            }
        )
    df = pd.DataFrame(rows).sort_values("Signal Score", ascending=False)

    scatter = (
        alt.Chart(df)
        .mark_circle(opacity=0.85)
        .encode(
            x=alt.X("Reach %:Q", title="Reach (% of corpus)", axis=_AXIS),
            y=alt.Y("Impact:Q", title="Impact (blended severity)", axis=_AXIS),
            size=alt.Size("Confidence:Q", title="Confidence", scale=alt.Scale(range=[80, 900])),
            color=alt.Color(
                "Feasible w/o $:N",
                title="Feasible without $",
                scale=alt.Scale(
                    domain=["yes", "partial", "no"],
                    range=[_FEASIBILITY_COLORS["yes"], _FEASIBILITY_COLORS["partial"], _FEASIBILITY_COLORS["no"]],
                ),
            ),
            tooltip=["Opportunity", "Reach %", "Impact", "Confidence", "Signal Score", "Feasible w/o $", "Matched reviews"],
        )
        .properties(height=360, background="transparent")
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(scatter, use_container_width=True)

    render_html('<div class="rd-section-title" style="font-size:1rem;margin-top:1.2rem;">Ranked table</div>')
    st.dataframe(
        df[["Opportunity", "Reach %", "Impact", "Confidence", "Signal Score", "Feasible w/o $", "Matched reviews"]],
        use_container_width=True,
        hide_index=True,
    )

    render_html('<div class="rd-section-title" style="font-size:1rem;margin-top:1.2rem;">Synthesis & quotes</div>')
    for op in sorted(data.opportunities, key=lambda o: o["signal_score"], reverse=True):
        feasible = op["feasible_without_monetary_incentive"]
        badge_color = _FEASIBILITY_COLORS.get(feasible, "#B6ABB6")
        with st.expander(f"{op['label']}  ·  signal {op['signal_score']}  ·  reach {op['reach']['pct']}%"):
            render_html(
                f'<span class="rd-badge" style="background:rgba(255,255,255,.08);color:{badge_color};">'
                f'feasible without $: {esc(feasible)}</span>'
            )
            if op.get("llm_synthesis"):
                render_html(f'<div class="rd-card-desc" style="margin-top:.6rem;">{esc(op["llm_synthesis"])}</div>')
            else:
                render_html(
                    '<div class="rd-card-desc" style="margin-top:.6rem;color:#7d7377;">'
                    'No LLM synthesis yet for this area (rule-based reach only).</div>'
                )
            for q in op.get("top_quotes", []):
                render_html(
                    f'<div class="rd-quote">"{esc(q["text"])}" '
                    f'<span style="color:#7d7377;">— {stars(q["rating"])} {esc(q["platform"])}, {esc(q["date"])}, '
                    f'id {esc(q["review_id"][:8])}</span></div>'
                )


def render_live_chat(retriever: ReviewRetriever) -> None:
    render_html(
        '<div class="rd-section-title">Live Chat</div>'
        '<div class="rd-section-sub">Ask grounded questions over the review corpus — wishlist behavior, '
        'fit/size, comparison shopping, trust, and more.</div>'
    )

    api_key_set = bool(get_secret("GROQ_API_KEY"))
    status_label = "LLM Online" if api_key_set else "LLM Offline (retrieval-only)"
    status_color = MYNTRA_ORANGE if api_key_set else "#FF6B6B"

    remaining = groq_budget.remaining_capacity()
    render_html(
        f'<div class="rd-pill-row">'
        f'<span class="rd-badge" style="background:rgba(255,138,0,.15);color:{status_color};">{status_label}</span>'
        f'<span class="rd-badge muted">{retriever.corpus_size:,} reviews indexed</span>'
        f'<span class="rd-badge muted">Groq budget today: {remaining["daily_calls_remaining"]} calls / '
        f'{remaining["daily_tokens_remaining"]:,} tokens left</span>'
        f'</div>'
    )
    render_html(
        '<div style="color:#7d7377;font-size:.78rem;margin:.3rem 0 .8rem;">'
        'If the shared Groq budget (also used by the batch analysis job) is tight, answers '
        'automatically fall back to a free, retrieval-only mode — never an error.</div>'
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.caption("Quick starter questions:")
    sug_cols = st.columns(2)
    starters = [
        "Why do users hesitate to buy items they've wishlisted?",
        "How do users compare multiple shortlisted products?",
        "What do users say about fit and size uncertainty?",
        "When is the wishlist genuine purchase intent vs. just bookmarking?",
    ]
    for i, q in enumerate(starters):
        if sug_cols[i % 2].button(q, key=f"chat_sugg_{i}", use_container_width=True):
            with st.spinner("Searching vector index & generating grounded answer..."):
                res = answer_question(q, retriever)
            st.session_state.chat_history.append((q, res))
            st.rerun()

    with st.form("wishlist_chat_form", clear_on_submit=True):
        prompt = st.text_input(
            "Ask a question about wishlist behavior or purchase decisions",
            placeholder="e.g. Why do users wait instead of buying wishlisted items?",
        )
        submitted = st.form_submit_button("Submit Question", use_container_width=True)

    if submitted and prompt.strip():
        with st.spinner("Searching vector index & generating grounded answer..."):
            res = answer_question(prompt, retriever)
        st.session_state.chat_history.append((prompt, res))
        st.rerun()

    for question, result in reversed(st.session_state.chat_history[-5:]):
        render_html(
            f'<div class="rd-card" style="border-left:3px solid #351F50;">'
            f'<div class="rd-meta" style="margin-bottom:.35rem;"><span>QUESTION</span></div>'
            f'<div style="color:#fff;font-weight:600;">{esc(question)}</div>'
            f'</div>'
        )
        render_html(
            f'<div class="rd-card accent" style="border-left:3px solid #FF8A00;">{format_chat_answer(result.answer)}</div>'
        )
        if result.meta.get("fallback_reason"):
            render_html(
                f'<div style="color:#7d7377;font-size:.74rem;margin:-.4rem 0 .6rem;">'
                f'Offline/fallback answer — reason: {esc(result.meta["fallback_reason"])}</div>'
            )

        if result.retrieved:
            with st.expander(f"View grounded review sources ({len(result.retrieved)} reviews)"):
                for item in result.retrieved:
                    doc = esc(item.document[:300]) + ("…" if len(item.document) > 300 else "")
                    render_html(
                        f'<div class="rd-card" style="margin-bottom:.4rem;padding:.7rem .9rem;">'
                        f'<div class="rd-meta">{stars(item.rating)} <span><b>{esc(item.date)}</b></span> '
                        f'<span class="rd-badge muted">{esc(item.platform)}</span> '
                        f'<span>match {item.similarity:.0%}</span> '
                        f'<span>id <b>{esc(item.review_id[:8])}</b></span></div>'
                        f'<div style="color:#D0D0D0;font-size:.85rem;margin-top:.3rem;">{doc}</div></div>'
                    )

    if st.session_state.chat_history and st.button("Clear Chat History", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()


def main() -> None:
    inject_global_css()

    try:
        data = _load_data()
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    render_header(data)

    nav_tabs = ["📊 Opportunity Scorecard", "💬 Live Chat"]
    with st.sidebar:
        st.markdown("## Navigation")
        active_tab = st.radio("Navigation Menu", nav_tabs, label_visibility="collapsed", key="active_nav_tab")
        if data.load_warnings:
            with st.expander("⚠️ Load warnings"):
                for w in data.load_warnings:
                    st.caption(w)

    if active_tab == nav_tabs[0]:
        render_opportunity_scorecard(data)
    elif active_tab == nav_tabs[1]:
        retriever = _get_retriever()
        render_live_chat(retriever)


if __name__ == "__main__":
    main()
