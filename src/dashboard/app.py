"""Streamlit dashboard — Myntra Wishlist Discovery Engine.

5 screens (Plan 3 Track B complete): Opportunity Scorecard, Live Chat,
Review Explorer, Opportunity Deep-Dive, Wishlist Segments.
"""

from __future__ import annotations

import os
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
from src.dashboard.constants import APP_TITLE, APP_SUBTITLE, LOGO_PATH
from src.dashboard.data_loader import load_dashboard_data
from src.dashboard.style import (
    inject_global_css,
    esc,
    format_chat_answer,
    render_html,
    review_card,
    stars,
    MYNTRA_ORANGE,
    MYNTRA_PINK,
)
from src.rag.pipeline import answer_question
from src.rag.retriever import ReviewRetriever
from src.analysis import budget as groq_budget
from src.analysis.taxonomy import TAXONOMY, classify_rule_based

apply_streamlit_secrets(st)
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

if LOGO_PATH.exists():
    # No icon_image passed -> Streamlit keeps showing `image` top-left
    # whether the sidebar is expanded or collapsed (per st.logo's own docs).
    st.logo(str(LOGO_PATH), size="large")

_AXIS = alt.Axis(
    labelColor="#231F20",
    titleColor="#231F20",
    gridColor="#EDE4E9",
    tickColor="#D8CCD3",
    labelLimit=1000,
    labelFontSize=11,
)

_FEASIBILITY_COLORS = {"yes": "#1FA463", "partial": "#C98A00", "no": "#E0294B"}
_PAGE_SIZE = 15

_PLATFORM_DISPLAY_NAMES = {
    "google_play": "Google Play",
    "app_store": "App Store",
    "youtube": "YouTube",
    "mouthshut": "MouthShut",
    "x": "X (Twitter)",
}


@st.cache_resource(show_spinner="Connecting to vector search index...")
def _get_retriever() -> ReviewRetriever:
    return ReviewRetriever()


@st.cache_data(show_spinner="Loading opportunity-analysis artifacts...")
def _load_data():
    return load_dashboard_data()


def trigger_github_action() -> tuple[bool, str]:
    """Trigger the weekly_refresh.yml workflow on GitHub via REST API."""
    import requests
    token = get_secret("GITHUB_TOKEN") or get_secret("GH_PAT")
    if not token:
        return False, "GITHUB_TOKEN not found in secrets."

    owner = get_secret("GITHUB_OWNER", "the-machine-learner")
    repo = get_secret("GITHUB_REPO", "myntra-review-discovery-engine")
    workflow_id = "weekly_refresh.yml"
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"ref": "main"}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 204:
            return True, "GitHub Action dispatched successfully!"
        return False, f"GitHub API status {res.status_code}: {res.text}"
    except Exception as exc:
        return False, f"Request failed: {exc}"


def handle_pipeline_refresh():
    """Run full simulated refresh pipeline across all stages (ingest -> embed -> Groq analysis)."""
    st.session_state["show_refresh_notice"] = True
    ok, msg = trigger_github_action()
    if ok:
        st.toast("⚡ Live run dispatched on GitHub Actions!", icon="⚡")
    else:
        with st.spinner("Running incremental review refresh & analysis pipeline..."):
            from src.ops.run import run_refresh_pipeline
            run_refresh_pipeline(incremental=True, simulated_analysis=True)
            _load_data.clear()
            _get_retriever.clear()
            st.toast("Pipeline refresh completed successfully!", icon="⚡")
    st.rerun()


def render_header(data) -> None:
    from src.dashboard.pipeline_status import get_pipeline_status
    status = get_pipeline_status()

    sources = sorted({r.platform for r in data.reviews})
    source_names = ", ".join(
        _PLATFORM_DISPLAY_NAMES.get(s, s.replace("_", " ").title()) for s in sources
    )

    head_left, head_right = st.columns([1.5, 1], gap="medium")

    with head_left:
        render_html(
            f"""
            <div>
              <div style="font-size:1.6rem;font-weight:900;color:#231F20;letter-spacing:-.02em;">
                🛍️ {esc(APP_TITLE)}
              </div>
              <div style="color:#6E6470;font-size:.92rem;margin-top:.2rem;">{esc(APP_SUBTITLE)}</div>
              <div style="color:#6E6470;font-size:.78rem;margin-top:.15rem;">Sourced from {esc(source_names)} reviews</div>
            </div>
            """
        )

    with head_right:
        online_badge = (
            '<div class="pipeline-status-badge"><span class="pipeline-status-dot"></span><span class="pipeline-status-text">Pipeline online</span></div>'
            if status.online else
            '<div class="pipeline-status-badge" style="background:#FFF0F2;border-color:#E0294B;"><span class="pipeline-status-dot" style="background:#E0294B;box-shadow:0 0 6px #E0294B;"></span><span class="pipeline-status-text" style="color:#C81E36;">Pipeline offline</span></div>'
        )
        render_html(
            f"""
            <div style="display:flex;flex-direction:column;align-items:flex-end;text-align:right;gap:.25rem;margin-bottom:.4rem;width:100%;">
              {online_badge}
              <div style="text-align:right;font-size:.84rem;color:#231F20;font-weight:700;margin-top:.1rem;">
                Synced <span style="font-weight:900;color:#231F20;">{status.synced_label}</span>
              </div>
              <div style="text-align:right;font-size:.76rem;color:#6E6470;font-weight:600;">
                {status.synced_local}
              </div>
            </div>
            """
        )
        _, btn_col = st.columns([1.2, 1])
        with btn_col:
            if st.button("Refresh pipeline", use_container_width=True, key="header_refresh_pipeline_btn"):
                handle_pipeline_refresh()

        if st.session_state.get("show_refresh_notice"):
            render_html(
                """
                <div style="background:#FFF5FB;border:1px solid #F41CB2;border-radius:10px;padding:.65rem .85rem;margin-top:.6rem;font-size:.82rem;color:#231F20;line-height:1.4;">
                  ⚡ Live run started — track it on <a href="https://github.com/the-machine-learner/myntra-review-discovery-engine/actions/workflows/weekly_refresh.yml" target="_blank" style="color:#F41CB2;font-weight:700;text-decoration:underline;">GitHub Actions</a>. New numbers appear automatically once the run commits and the app redeploys (~6 min).
                </div>
                """
            )

    meta = data.opportunity_run_metadata
    if not meta:
        render_html(
            '<div class="rd-card" style="border-left:3px solid #C98A00;">'
            '<b style="color:#9C6B00;">No analysis run yet.</b> '
            '<span style="color:#6E6470;">Showing the ingested corpus only. Run '
            '<code>python -m src.analysis.run</code> to populate the Opportunity Scorecard.</span>'
            '</div>'
        )
    else:
        cols = st.columns(3)
        cols[0].metric("Corpus size", f"{meta.get('corpus_size_at_run', len(data.reviews)):,}")
        cols[1].metric("Data sources", len(sources))
        cols[2].metric("Opportunity areas analysed", len(data.opportunities))


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
        .configure_legend(
            titleColor="#231F20",
            labelColor="#231F20",
        )
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
        badge_color = _FEASIBILITY_COLORS.get(feasible, "#6E6470")
        with st.expander(f"{op['label']}  ·  signal {op['signal_score']}  ·  reach {op['reach']['pct']}%"):
            render_html(
                f'<span class="rd-badge" style="background:rgba(0,0,0,.05);color:{badge_color};">'
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


def render_review_explorer(data) -> None:
    render_html(
        '<div class="rd-section-title">Review Explorer</div>'
        f'<div class="rd-section-sub">Browse, search, and filter all {len(data.reviews):,} normalized reviews '
        'in the dataset — including by which opportunity-area keywords they match.</div>'
    )

    all_reviews = data.reviews
    fcol, rcol = st.columns([1, 2.6], gap="large")

    platforms = sorted({r.platform for r in all_reviews})
    area_options = ["All"] + [TAXONOMY[aid].label for aid in TAXONOMY]
    area_label_to_id = {TAXONOMY[aid].label: aid for aid in TAXONOMY}

    with fcol:
        render_html('<div class="rd-card-title">Search & Filters</div>')
        query = st.text_input("Search review text", placeholder="Keywords: size, wishlist, sale, delivery")
        rating_choice = st.radio("Rating filter", ["All", "5★", "4★", "3★", "2★", "1★"], horizontal=True, key="exp_rating")
        platform_choice = st.selectbox("Platform filter", ["All"] + platforms)
        area_choice = st.selectbox(
            "Opportunity-area filter (rule-based keyword match)", area_options, key="exp_area"
        )
        sort_choice = st.selectbox("Sort order", ["Newest first", "Oldest first", "Most helpful", "Lowest rating", "Highest rating"])
        if st.button("Reset Filters", use_container_width=True):
            st.session_state.pop("exp_rating", None)
            st.session_state.pop("exp_area", None)
            st.rerun()

    # Apply filters
    filtered = all_reviews
    if query.strip():
        q = query.strip().lower()
        filtered = [r for r in filtered if q in r.body.lower()]
    if rating_choice != "All":
        target = int(rating_choice[0])
        filtered = [r for r in filtered if r.rating == target]
    if platform_choice != "All":
        filtered = [r for r in filtered if r.platform == platform_choice]
    if area_choice != "All":
        target_area_id = area_label_to_id[area_choice]
        filtered = [r for r in filtered if target_area_id in classify_rule_based(r.body)]

    if sort_choice == "Newest first":
        filtered = sorted(filtered, key=lambda r: r.date, reverse=True)
    elif sort_choice == "Oldest first":
        filtered = sorted(filtered, key=lambda r: r.date)
    elif sort_choice == "Most helpful":
        filtered = sorted(filtered, key=lambda r: r.thumbs_up, reverse=True)
    elif sort_choice == "Lowest rating":
        filtered = sorted(filtered, key=lambda r: r.rating)
    else:
        filtered = sorted(filtered, key=lambda r: r.rating, reverse=True)

    avg = round(sum(r.rating for r in filtered) / len(filtered), 2) if filtered else 0.0

    with rcol:
        m1, m2, m3 = st.columns(3)
        m1.metric("Matching Reviews", f"{len(filtered):,}")
        m2.metric("Avg Rating", f"{avg}★")
        m3.metric("Total Corpus Size", f"{len(all_reviews):,}")

        if not filtered:
            st.info("No reviews match the selected filter criteria.")
            return

        sig = (query.strip().lower(), rating_choice, platform_choice, area_choice, sort_choice)
        if st.session_state.get("exp_filter_sig") != sig:
            st.session_state["exp_filter_sig"] = sig
            st.session_state["exp_page"] = 0

        total_pages = max(1, (len(filtered) + _PAGE_SIZE - 1) // _PAGE_SIZE)
        page = min(st.session_state.get("exp_page", 0), total_pages - 1)
        start = page * _PAGE_SIZE
        end = min(start + _PAGE_SIZE, len(filtered))

        render_html(
            f"""
            <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:.6rem;">
              <div class="rd-card-title">Corpus Reviews</div>
              <div style="color:#6E6470;font-size:.8rem;">Showing {start + 1:,}–{end:,} of {len(filtered):,}</div>
            </div>
            """
        )

        for r in filtered[start:end]:
            render_html(review_card(
                review_id=r.review_id, rating=r.rating, date=r.date,
                app_version=r.app_version, body=r.body, platform=r.platform,
                thumbs_up=r.thumbs_up
            ))

        prev_col, info_col, next_col = st.columns([1, 1.6, 1])
        with prev_col:
            if st.button("← Previous", use_container_width=True, disabled=page <= 0, key="exp_prev"):
                st.session_state["exp_page"] = page - 1
                st.rerun()
        with info_col:
            render_html(
                f'<div style="text-align:center;color:#6E6470;font-size:.85rem;padding-top:.45rem;">'
                f'Page <b style="color:#231F20;">{page + 1}</b> of {total_pages}</div>'
            )
        with next_col:
            if st.button("Next →", use_container_width=True, disabled=page >= total_pages - 1, key="exp_next"):
                st.session_state["exp_page"] = page + 1
                st.rerun()


def render_opportunity_deep_dive(data, retriever: ReviewRetriever) -> None:
    render_html(
        '<div class="rd-section-title">Opportunity Deep-Dive</div>'
        '<div class="rd-section-sub">Pick one opportunity area to drill into its full synthesis, '
        'quotes, and a chat scoped ONLY to reviews tagged for that area.</div>'
    )

    scored_by_id = {op["area_id"]: op for op in data.opportunities}
    area_ids_ranked = sorted(
        TAXONOMY.keys(),
        key=lambda aid: scored_by_id.get(aid, {}).get("signal_score", -1),
        reverse=True,
    )
    labels = [f'{TAXONOMY[aid].label}{"  (scored)" if aid in scored_by_id else "  (not yet analyzed)"}' for aid in area_ids_ranked]
    label_to_area_id = dict(zip(labels, area_ids_ranked))

    chosen_label = st.selectbox("Opportunity area", labels, key="deepdive_area")
    area_id = label_to_area_id[chosen_label]
    area = TAXONOMY[area_id]

    render_html(
        f'<div class="rd-card" style="border-left:3px solid {MYNTRA_PINK};">'
        f'<div class="rd-card-title">{esc(area.label)}</div>'
        f'<div class="rd-card-desc">{esc(area.description)}</div>'
        f'<div class="rd-meta" style="margin-top:.4rem;">'
        f'<span>Anchor questions: {esc("; ".join(area.anchor_questions))}</span></div>'
        f'</div>'
    )

    op = scored_by_id.get(area_id)
    if op:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Reach", f'{op["reach"]["pct"]}%')
        c2.metric("Impact", op["impact"]["blended_impact_score"])
        c3.metric("Confidence", op["confidence"]["confidence_score"])
        c4.metric("Signal Score", op["signal_score"])

        if op.get("llm_synthesis"):
            render_html(f'<div class="rd-card-desc" style="margin-top:.8rem;">{esc(op["llm_synthesis"])}</div>')
        for q in op.get("top_quotes", []):
            render_html(
                f'<div class="rd-quote">"{esc(q["text"])}" '
                f'<span style="color:#7d7377;">— {stars(q["rating"])} {esc(q["platform"])}, {esc(q["date"])}, '
                f'id {esc(q["review_id"][:8])}</span></div>'
            )
    else:
        render_html(
            '<div class="rd-card-desc" style="color:#7d7377;margin-top:.6rem;">'
            'No scored synthesis yet for this area — run '
            f'<code>python -m src.analysis.run --areas {area_id}</code> to populate it. '
            'The scoped chat below still works off rule-based tagging alone.</div>'
        )

    render_html('<div class="rd-section-title" style="font-size:1rem;margin-top:1.4rem;">Scoped chat — this area only</div>')

    where = {f"tag_{area_id}": True}
    history_key = f"deepdive_chat_{area_id}"
    if history_key not in st.session_state:
        st.session_state[history_key] = []

    with st.form(f"deepdive_chat_form_{area_id}", clear_on_submit=True):
        prompt = st.text_input(
            f"Ask a question scoped to \"{area.label}\" reviews only",
            placeholder="e.g. What specifically frustrates users about this?",
            key=f"deepdive_prompt_{area_id}",
        )
        submitted = st.form_submit_button("Ask", use_container_width=True)

    if submitted and prompt.strip():
        with st.spinner("Searching this area's reviews & generating grounded answer..."):
            res = answer_question(prompt, retriever, where=where)
        st.session_state[history_key].append((prompt, res))
        st.rerun()

    for question, result in reversed(st.session_state[history_key][-3:]):
        render_html(
            f'<div class="rd-card" style="border-left:3px solid {MYNTRA_PINK};">'
            f'<div class="rd-meta" style="margin-bottom:.35rem;"><span>QUESTION</span></div>'
            f'<div style="color:#231F20;font-weight:600;">{esc(question)}</div>'
            f'</div>'
        )
        render_html(
            f'<div class="rd-card accent" style="border-left:3px solid {MYNTRA_ORANGE};">{format_chat_answer(result.answer)}</div>'
        )
        if result.retrieved:
            with st.expander(f"View grounded sources ({len(result.retrieved)} reviews)"):
                for item in result.retrieved:
                    doc = esc(item.document[:300]) + ("…" if len(item.document) > 300 else "")
                    render_html(
                        f'<div class="rd-card" style="margin-bottom:.4rem;padding:.7rem .9rem;">'
                        f'<div class="rd-meta">{stars(item.rating)} <span><b>{esc(item.date)}</b></span> '
                        f'<span class="rd-badge muted">{esc(item.platform)}</span> '
                        f'<span>match {item.similarity:.0%}</span> '
                        f'<span>id <b>{esc(item.review_id[:8])}</b></span></div>'
                        f'<div style="color:#3A323C;font-size:.85rem;margin-top:.3rem;">{doc}</div></div>'
                    )


_SEGMENT_COLORS = {
    "genuine_purchase_intent": "#1FA463",
    "price_watch": MYNTRA_ORANGE,
    "bookmark_no_intent": "#E0294B",
    "gift": "#8E44C7",
    "inspiration_board": "#2E8FCB",
    "unclear": "#7d7377",
}


def render_wishlist_segments(data) -> None:
    render_html(
        '<div class="rd-section-title">Wishlist Segments</div>'
        '<div class="rd-section-sub">Why do people wishlist at all? Reviews that mention wishlist behavior, '
        'classified into one of 5 usage modes.</div>'
    )

    seg_data = data.wishlist_segments
    segments = seg_data.get("segments", [])
    meta = seg_data.get("run_metadata", {})

    if not segments:
        render_html(
            '<div class="rd-card">No segmentation run yet. From a shell: '
            '<code>python -c "from src.analysis.pipeline import load_reviews; '
            'from src.analysis.segments import run_segmentation; from pathlib import Path; '
            'run_segmentation(load_reviews(Path(\'data/processed/normalized_reviews.json\')))"</code></div>'
        )
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Candidate reviews (mention wishlist)", f'{meta.get("candidate_pool_size", 0):,}')
    c2.metric("Classified", f'{meta.get("total_classified", 0):,}')
    c3.metric("Groq calls (last run)", meta.get("groq_call_count", 0))

    render_html(
        '<div style="color:#7d7377;font-size:.78rem;margin:.4rem 0 1rem;">'
        'Small numbers here are expected and honest — most of this corpus is star-rating app reviews '
        '(delivery/refund/quality complaints), not reflective wishlist narratives. See the Opportunity '
        'Deep-Dive screen for the same caveat on 3 taxonomy areas.</div>'
    )

    df = pd.DataFrame(
        [{"Segment": s["label"], "Count": s["count"], "segment_id": s["segment_id"]} for s in segments]
    )
    if df["Count"].sum() > 0:
        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("Count:Q", title="Reviews", axis=_AXIS),
                y=alt.Y("Segment:N", sort="-x", title=None, axis=_AXIS),
                color=alt.Color(
                    "segment_id:N",
                    scale=alt.Scale(domain=list(_SEGMENT_COLORS.keys()), range=list(_SEGMENT_COLORS.values())),
                    legend=None,
                ),
                tooltip=["Segment", "Count"],
            )
            .properties(height=280, background="transparent")
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, use_container_width=True)

    for s in segments:
        if s["count"] == 0:
            continue
        color = _SEGMENT_COLORS.get(s["segment_id"], "#6E6470")
        with st.expander(f'{s["label"]}  ·  {s["count"]} reviews ({s["pct_of_classified"]}%)'):
            render_html(
                f'<span class="rd-badge" style="background:rgba(0,0,0,.05);color:{color};">'
                f'{esc(s["segment_id"])}</span>'
                f'<div class="rd-card-desc" style="margin-top:.6rem;">{esc(s["description"])}</div>'
            )
            for q in s.get("quotes", []):
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
    status_color = MYNTRA_ORANGE if api_key_set else "#E0294B"

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
            f'<div class="rd-card" style="border-left:3px solid {MYNTRA_PINK};">'
            f'<div class="rd-meta" style="margin-bottom:.35rem;"><span>QUESTION</span></div>'
            f'<div style="color:#231F20;font-weight:600;">{esc(question)}</div>'
            f'</div>'
        )
        render_html(
            f'<div class="rd-card accent" style="border-left:3px solid {MYNTRA_ORANGE};">{format_chat_answer(result.answer)}</div>'
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
                        f'<div style="color:#3A323C;font-size:.85rem;margin-top:.3rem;">{doc}</div></div>'
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

    nav_tabs = [
        "📊 Opportunity Scorecard",
        "💬 Live Chat",
        "🔍 Review Explorer",
        "🔬 Opportunity Deep-Dive",
        "🧩 Wishlist Segments",
    ]
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=160)
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
    elif active_tab == nav_tabs[2]:
        render_review_explorer(data)
    elif active_tab == nav_tabs[3]:
        retriever = _get_retriever()
        render_opportunity_deep_dive(data, retriever)
    else:
        render_wishlist_segments(data)


if __name__ == "__main__":
    main()
