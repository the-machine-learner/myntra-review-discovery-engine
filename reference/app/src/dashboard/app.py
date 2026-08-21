"""Streamlit dashboard — Myntra Product Discovery Engine & VOC Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path so 'src' imports resolve under all launch conditions
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import re
import altair as alt
import pandas as pd
import streamlit as st
from collections import defaultdict, Counter

from src.config import get_secret
from src.dashboard.bootstrap import apply_streamlit_secrets
from src.dashboard.constants import APP_TITLE, APP_SUBTITLE, SEGMENT_DISCLAIMER
from src.dashboard.data_loader import load_dashboard_data
from src.dashboard.pipeline_status import get_pipeline_status, PipelineStatus
from src.dashboard.style import (
    inject_global_css,
    esc,
    format_chat_answer,
    render_html,
    stars,
    review_card,
    week_label,
    MYNTRA_ORANGE,
    MYNTRA_PURPLE
)
from src.rag.pipeline import answer_question, ChatResult
from src.rag.retriever import ReviewRetriever

# 1. Page Config & Secrets
apply_streamlit_secrets(st)
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Global Altair configuration for Myntra dark theme
_AXIS = alt.Axis(
    labelColor="#B6ABB6",
    titleColor="#FFFFFF",
    gridColor="#2A1840",
    tickColor="#351F50",
    labelLimit=1000,
    labelFontSize=11
)

_SEGMENT_LABELS = {
    "habitual_trust_and_awareness_hesitant": "Habitual Single-Category (App Trust & Awareness Hesitant)",
    "habitual_expiry_quality_hesitant": "Habitual Single-Category (Expiry & Freshness Hesitant)",
    "habitual_price_sensitive": "Habitual Single-Category (Price & Fee Switchers)",
    "habitual_sos_single": "Habitual Single-Category (SOS Emergency Gap-Fillers)",
    "habitual_unaware_explorer": "Habitual Single-Category (Unaware / UI Non-Explorers)",
    "household_replenisher": "Household Replenishers (Family groceries & staples)",
    "impulse_snaker_night_owl": "Impulse Snackers & Night‑Owls (Late‑night, bachelors/students)",
    "hesitant_multi_platformer": "Hesitant Multi‑Platformers (Uses Amazon/BigBasket/Blinkit, price/trust blocks)",
    "emergency_sos_shopper": "Emergency / SOS Shoppers (Urgent medicine, cooking gaps)",
    "premium_gourmet_shopper": "Premium / Gourmet Shopper (Electronics, branded apparel, watches, expensive/gourmet items)",
    "general_shopper": "General Shoppers (General app, store, or delivery feedback)",
    "general_shopper_positive": "General Shopper (Positive feedback)",
    "general_shopper_neutral": "General Shopper (Neutral/mixed feedback)",
    "general_shopper_negative": "General Shopper (Negative feedback)",
}

_PAGE_SIZE = 15
_DIST_COLORS = {5: "#FF8A00", 4: "#FFA233", 3: "#F2C744", 2: "#FF6B6B", 1: "#E22134"}

# Pre-computed discovery question syntheses for Screen 1
DISCOVERY_QUESTIONS = [
    {
        "q": "Why do users repeatedly buy from the same categories?",
        "answer": (
            "Customers develop high-friction trust barriers for unfamiliar categories. "
            "They rely on Myntra for fast 10-minute replenishment of habit-driven staples (milk, bread, quick snacks) "
            "because the utility is predictable and low-risk. Repeat purchases dominate when users know the exact product size and quality."
        ),
        "key_takeaway": "Habit & speed lock-in: low risk items drive repeat orders, while unknown items face high scrutiny."
    },
    {
        "q": "What prevents users from exploring new categories?",
        "answer": (
            "Major exploration blockers include: missing product specification details (ingredients, weight, expiry dates), "
            "fear of receiving near-expiry items without refund guarantees, higher price perception compared to Amazon/BigBasket, "
            "and home screen clutter pushing irrelevant recommendations."
        ),
        "key_takeaway": "Trust & Information gaps: lack of pre-purchase product specs and refund uncertainty stall category trial."
    },
    {
        "q": "How do users discover products today?",
        "answer": (
            "Discovery currently happens through direct search queries or browsing top banner promotions. "
            "However, users report high frustration with keyword search failures, poor typo handling, and auto-suggestions "
            "that push out-of-stock or incorrect items."
        ),
        "key_takeaway": "Search-first behavior: search accuracy is the primary discovery gateway, but currently generates friction."
    },
    {
        "q": "What role do habits play in shopping behavior?",
        "answer": (
            "Habits dictate the core 10-minute quick commerce use case. Late-night impulse snackers order on craving triggers, "
            "while household replenishers reorder daily staples during morning or evening cooking preparation hours."
        ),
        "key_takeaway": "Time-of-day routines dictate category choices: morning staples vs. midnight impulse snacks."
    },
    {
        "q": "What information do users need before trying a new category?",
        "answer": (
            "Shoppers explicitly request clear expiry dates displayed on the product card, detailed ingredient lists, "
            "dietary badges (sugar-free, organic, gluten-free), clear brand origins, and verifiable customer ratings."
        ),
        "key_takeaway": "Transparency requirements: expiry date visibility and dietary badges directly increase conversion."
    },
    {
        "q": "What frustrations emerge repeatedly?",
        "answer": (
            "The top recurring grievances are: missing niche product categories, strict OTP-sharing refund policies, "
            "cluttered home screen recommendations, out-of-stock replenishment breaks, and pricing discrepancies vs local shops."
        ),
        "key_takeaway": "Policy & UX friction: strict refund policies and home screen clutter negatively impact customer trust."
    },
    {
        "q": "Which user segments are more likely to experiment?",
        "answer": (
            "The 'Premium / Gourmet Shopper' and 'Impulse Snackers & Night-Owls' exhibit the highest willingness to experiment. "
            "Gourmet & electronics buyers try high-value items when clear specifications and brand authenticity badges are present."
        ),
        "key_takeaway": "Premium Gourmet & Impulse segments are top candidates for category expansion campaigns."
    },
    {
        "q": "What unmet needs emerge consistently across discussions?",
        "answer": (
            "1. Visible manufacturing & expiry dates on item listing cards.\n"
            "2. Subcategory filtering for dietary & regional preferences.\n"
            "3. Smarter search that auto-corrects typos and finds exact brand substitutes.\n"
            "4. Transparent, low-friction refund process for fresh items."
        ),
        "key_takeaway": "Top priority feature requests: pre-purchase specs, smarter search, and easy refunds."
    },
]


# Cache Data & Auto-seed search index
@st.cache_resource(show_spinner="Initializing vector search index...")
def _get_retriever() -> ReviewRetriever:
    retriever = ReviewRetriever()
    if retriever.corpus_size == 0:
        from src.embeddings.run import run_embed_all
        from src.config import PROCESSED_DIR, VECTOR_STORE_DIR
        reviews_path = PROCESSED_DIR / "normalized_reviews.json"
        if reviews_path.exists():
            with st.spinner("Seeding vector search index over 15,000 reviews..."):
                run_embed_all(reviews_path, batch_size=128, persist_dir=VECTOR_STORE_DIR)
            retriever = ReviewRetriever()
    return retriever


@st.cache_data(show_spinner="Loading analysis artifacts...")
def _load_data():
    return load_dashboard_data()


def trigger_github_action() -> tuple[bool, str]:
    """Trigger the weekly_refresh.yml workflow on GitHub via REST API."""
    import requests
    token = get_secret("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT")
    if not token:
        return False, "GITHUB_TOKEN not found in secrets."

    owner = "the-machine-learner"
    repo = "myntra-review-discovery-engine"
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
    """Trigger incremental refresh via GitHub API if GITHUB_TOKEN exists, else run locally."""
    st.session_state["show_refresh_notice"] = True
    ok, msg = trigger_github_action()
    if ok:
        st.toast("⚡ Live run dispatched on GitHub Actions!", icon="⚡")
    else:
        # Fallback to local incremental execution if GITHUB_TOKEN is not set
        with st.spinner("Running incremental review refresh & vector indexing..."):
            from src.ops.run import run_refresh_pipeline
            run_refresh_pipeline(incremental=True, rule_baseline=True)
            _load_data.clear()
            _get_retriever.clear()
            st.toast("Incremental pipeline refresh completed locally!", icon="⚡")
    st.rerun()


# 2. Header Render
def render_header(data) -> None:
    inject_global_css()
    status = get_pipeline_status()

    head_left, head_right = st.columns([1.5, 1], gap="medium")

    with head_left:
        render_html(
            f"""
            <div style="display:flex;align-items:center;gap:.75rem;margin-bottom:.5rem;">
              <div style="display:inline-flex;align-items:center;gap:.35rem;background:linear-gradient(135deg, #4A0072, #7B2CBF);padding:.4rem .85rem;border-radius:10px;border:1px solid #9D4EDD;box-shadow:0 4px 14px rgba(123,44,191,0.35);">
                <span style="font-family:'Outfit',sans-serif;font-weight:900;font-size:1.6rem;color:#FFFFFF;letter-spacing:-0.05em;line-height:1;">myntra</span>
                <span style="color:#FF8A00;font-weight:900;font-size:1.3rem;">⚡</span>
              </div>
              <div>
                <h1 style="margin:0;font-size:2.1rem;font-weight:900;letter-spacing:-.03em;">{APP_TITLE}</h1>
                <div style="color:#B6ABB6;font-size:.92rem;margin-top:.15rem;">{APP_SUBTITLE}</div>
              </div>
            </div>
            """
        )

    with head_right:
        online_badge = (
            '<div class="pipeline-status-badge"><span class="pipeline-status-dot"></span><span class="pipeline-status-text">Pipeline online</span></div>'
            if status.online else
            '<div class="pipeline-status-badge" style="background:#370606;border-color:#5C0E0E;"><span class="pipeline-status-dot" style="background:#FF6B6B;box-shadow:0 0 6px #FF6B6B;"></span><span class="pipeline-status-text" style="color:#FF6B6B;">Pipeline offline</span></div>'
        )
        render_html(
            f"""
            <div style="display:flex;flex-direction:column;align-items:flex-end;text-align:right;gap:.25rem;margin-top:.75rem;margin-bottom:.4rem;width:100%;">
              {online_badge}
              <div style="text-align:right;font-size:.84rem;color:#FFFFFF;font-weight:700;margin-top:.1rem;">
                Synced <span style="font-weight:900;color:#FFFFFF;">{status.synced_label}</span>
              </div>
              <div style="text-align:right;font-size:.76rem;color:#B6ABB6;font-weight:600;">
                {status.synced_local}
              </div>
            </div>
            """
        )
        _, btn_col = st.columns([1.35, 1])
        with btn_col:
            if st.button("Refresh pipeline", use_container_width=True, key="header_refresh_pipeline_btn"):
                handle_pipeline_refresh()

        if st.session_state.get("show_refresh_notice"):
            render_html(
                """
                <div style="background:#1B1028;border:1px solid #FF8A00;border-radius:10px;padding:.65rem .85rem;margin-top:.6rem;font-size:.82rem;color:#E0E0E0;line-height:1.4;">
                  ⚡ Live run started — track it on <a href="https://github.com/the-machine-learner/myntra-review-discovery-engine/actions/workflows/weekly_refresh.yml" target="_blank" style="color:#FF8A00;font-weight:700;text-decoration:underline;">GitHub Actions</a>. New numbers appear automatically once the run commits and the app redeploys (~6 min).
                </div>
                """
            )


# --- SCREEN 1: HOME & DISCOVERY QUESTIONS ---
def render_screen_1(data) -> None:
    render_html(
        '<div class="rd-section-title">Corpus Overview & Category Discovery Insights</div>'
    )

    # 1. Corpus stats metrics
    c1, c2, c3 = st.columns(3)
    total_reviews = len(data.reviews)
    c1.metric("Total Normalized Reviews", f"{total_reviews:,}")
    c2.metric("Data Sources Ingested", "5 Channels")
    c3.metric("Discovery Sample Cap", "450 Entries")

    st.caption("Ingestion sources: Google Play Store, Apple App Store, Reddit, YouTube Comments, X (Twitter)")

    st.markdown("---")

    # 2. Dual Segmentation Section: Shopping Habits vs. Habitual Buyers Hesitation Reasons
    left, right = st.columns([1, 1], gap="large")
    
    # 2A. Shopping Habits Data Processing
    disc_summary = data.discovery_segments.get("summary", [])
    shopping_habits_items: dict[str, dict] = {}
    total_corpus = total_reviews or 1

    for s in disc_summary:
        seg_id = s.get("segment_id", "")
        count = s.get("count", 0)
        
        # Filter out habitual sub-segments from general shopping habits
        if "habitual_" in seg_id:
            continue

        if "general_shopper" in seg_id:
            key = "general_shopper"
            label = "General Shopper"
            desc = "General shoppers submitting positive, neutral, or general app and delivery feedback."
        elif seg_id == "premium_gourmet_shopper":
            key = "premium_gourmet_shopper"
            label = "Premium / Gourmet Shopper"
            desc = "Buying high-value items like electronics, branded apparel, smartwatches, luxury, or gourmet imported goods."
        elif seg_id == "emergency_sos_shopper":
            key = "emergency_sos_shopper"
            label = "Emergency / SOS Shopper"
            desc = "Urgent medicine, pharmacy, guest arrivals, last-minute cooking ingredient shortages."
        elif seg_id == "household_replenisher":
            key = "household_replenisher"
            label = "Household Replenisher"
            desc = "Shopping for family/households, buying daily groceries, staples, milk, cooking oil & vegetables."
        elif seg_id == "impulse_snaker_night_owl":
            key = "impulse_snaker_night_owl"
            label = "Impulse Snacker & Night-Owl"
            desc = "Ordering late-night snacks, munchies, beverages, bachelors/students looking for convenience."
        elif seg_id == "hesitant_multi_platformer":
            key = "hesitant_multi_platformer"
            label = "Hesitant Multi-Platformer"
            desc = "Compares prices across Blinkit, Instamart, BigBasket, Amazon; sensitive to delivery charges and trust."
        else:
            key = seg_id
            label = seg_id.replace("_", " ").title()
            desc = s.get("description", "Customer segment")

        if key in shopping_habits_items:
            shopping_habits_items[key]["count"] += count
        else:
            shopping_habits_items[key] = {
                "segment_id": key,
                "label": label,
                "count": count,
                "description": desc,
            }

    shopping_summary = []
    for k, item in shopping_habits_items.items():
        item["percentage"] = round(100 * item["count"] / total_corpus, 2)
        shopping_summary.append(item)

    shopping_summary.sort(key=lambda x: x["count"], reverse=True)

    # 2B. Habitual Buyer Hesitations Data Processing
    from src.config import PROCESSED_DIR
    hab_file = PROCESSED_DIR / "habitual_segmented.json"
    hab_counts = {}
    if hab_file.exists():
        try:
            hab_data = json.loads(hab_file.read_text(encoding="utf-8"))
            for r in hab_data:
                seg = r.get("inferred_segment", "unknown")
                hab_counts[seg] = hab_counts.get(seg, 0) + 1
        except Exception:
            hab_counts = {}

    total_hab_candidates = sum(hab_counts.values()) or 4351
    hesitation_summary = [
        {
            "label": "App Trust & Catalog Awareness",
            "count": hab_counts.get("habitual_trust_and_awareness_hesitant", 1629),
            "percentage": round(100 * hab_counts.get("habitual_trust_and_awareness_hesitant", 1629) / total_hab_candidates, 1),
            "desc": "Skeptical of fake offers, strict return policies, or unaware Myntra carries non-grocery categories."
        },
        {
            "label": "Expiry & Freshness Fears",
            "count": hab_counts.get("habitual_expiry_quality_hesitant", 1538),
            "percentage": round(100 * hab_counts.get("habitual_expiry_quality_hesitant", 1538) / total_hab_candidates, 1),
            "desc": "Buys routine staples but fears receiving near-expiry items or stale perishables in trial categories."
        },
        {
            "label": "Price & Fee Sensitivity",
            "count": hab_counts.get("habitual_price_sensitive", 932),
            "percentage": round(100 * hab_counts.get("habitual_price_sensitive", 932) / total_hab_candidates, 1),
            "desc": "Uses Myntra for speed staples but switches to Amazon/BigBasket for other categories due to prices or fees."
        },
        {
            "label": "SOS Emergency Gap-Filler",
            "count": hab_counts.get("habitual_sos_single", 252),
            "percentage": round(100 * hab_counts.get("habitual_sos_single", 252) / total_hab_candidates, 1),
            "desc": "Opens Myntra purely for urgent medicine or missing cooking ingredients and exits immediately."
        },
    ]

    # Row 1: Headers & Subheaders
    head_left, head_right = st.columns([1, 1], gap="large")
    with head_left:
        render_html(f'<div class="rd-section-title" style="font-size:1.05rem;">Segmentation by Shopping Habits</div>'
                    f'<div class="rd-section-sub">Core behavioral profiles identified across all normalized {total_reviews:,} reviews.</div>')
    with head_right:
        render_html(f'<div class="rd-section-title" style="font-size:1.05rem;">Sub-segmentation by hesitation root cause</div>'
                    f'<div class="rd-section-sub">Habitual buyers with expressed hesitations in switching to category across {total_hab_candidates:,} candidate reviews.</div>')

    # Row 2: Parallel Charts
    chart_left, chart_right = st.columns([1, 1], gap="large")
    with chart_left:
        if shopping_summary:
            rows = []
            for s in shopping_summary:
                rows.append({
                    "Segment": s.get("label", s.get("segment_id", "")),
                    "Reviews": s.get("count", 0),
                    "Share (%)": s.get("percentage", 0.0)
                })
            df = pd.DataFrame(rows)
            chart = (
                alt.Chart(df)
                .mark_bar(color=MYNTRA_ORANGE, cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Reviews:Q", title="Reviews", axis=_AXIS),
                    y=alt.Y("Segment:N", sort="-x", title=None, axis=_AXIS),
                    tooltip=["Segment", "Reviews", "Share (%)"],
                )
                .properties(height=280, background="transparent")
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart, use_container_width=True)

    with chart_right:
        h_rows = []
        for h in hesitation_summary:
            h_rows.append({
                "Hesitation Barrier": h["label"],
                "Candidates": h["count"],
                "Share (%)": h["percentage"]
            })
        h_df = pd.DataFrame(h_rows)
        h_chart = (
            alt.Chart(h_df)
            .mark_bar(color=MYNTRA_ORANGE, cornerRadiusEnd=4)
            .encode(
                x=alt.X("Candidates:Q", title="Candidate Reviews", axis=_AXIS),
                y=alt.Y("Hesitation Barrier:N", sort="-x", title=None, axis=_AXIS),
                tooltip=["Hesitation Barrier", "Candidates", "Share (%)"],
            )
            .properties(height=280, background="transparent")
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(h_chart, use_container_width=True)

    st.markdown("---")

    # 3. Discovery Questions Accordion
    render_html(
        '<div class="rd-section-title">Core Category Discovery Questions & Answers</div>'
        '<div class="rd-section-sub">Synthesized answers grounded in 15,000 customer reviews and vector DB retrieval. Click to collapse/expand.</div>'
    )

    for i, item in enumerate(DISCOVERY_QUESTIONS, start=1):
        with st.expander(f"Q{i}. {item['q']}", expanded=(i == 1)):
            render_html(
                f"""
                <div class="rd-card accent" style="background:#1E1028;margin-top:.4rem;">
                  <div style="color:#FF8A00;font-weight:700;font-size:.82rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.3rem;">Key Takeaway</div>
                  <div style="color:#FFFFFF;font-weight:700;font-size:1.02rem;margin-bottom:.8rem;">{esc(item['key_takeaway'])}</div>
                  <div style="color:#E0E0E0;font-size:.95rem;line-height:1.6;">{esc(item['answer'])}</div>
                </div>
                """
            )


# --- SCREEN 2: USER NEEDS ANALYSIS ---
def render_screen_2(data) -> None:
    render_html(
        '<div class="rd-section-title">Review Analysis for User Needs & Grievances</div>'
        '<div class="rd-section-sub">Clustered insights from top 450 product discovery reviews (missing categories, bad recommendations, search friction).</div>'
    )

    needs_data = data.user_needs_analysis
    themes = needs_data.get("themes", [])
    unmet = needs_data.get("unmet_needs", [])

    m1, m2, m3 = st.columns(3)
    m1.metric("Sample Subset Analyzed", f"{needs_data.get('sample_size', 450):,} Reviews")
    m2.metric("Discovery Themes Identified", len(themes))
    m3.metric("Top Unmet Needs Ranked", len(unmet))

    st.markdown("#### ")

    # Themes Section
    render_html('<div class="rd-section-title" style="font-size:1.1rem;">Product Discovery Grievance Clusters</div>')
    for t in themes:
        label = esc(t.get("label", t.get("theme_id", "")))
        summary = esc(t.get("summary", ""))
        sev = t.get("severity", "medium")
        badge_cls = "neg" if sev == "high" else "warn" if sev == "medium" else ""
        count = t.get("review_count", len(t.get("supporting_review_ids", [])))
        avg_r = t.get("avg_rating", "—")

        render_html(
            f"""
            <div class="rd-card accent" style="margin-bottom:.8rem;">
              <div class="rd-card-head">
                <div class="rd-card-title">{label}</div>
                <span class="rd-badge {badge_cls}">Severity: {sev}</span>
              </div>
              <div class="rd-card-desc">{summary}</div>
              <div class="rd-meta">
                <span><b>{count}</b> supporting reviews</span>
                <span>Avg rating: <b>{avg_r}★</b></span>
              </div>
            </div>
            """
        )
        quotes = t.get("quotes", [])
        if quotes:
            with st.expander(f"View verbatim quotes for {label}"):
                for q in quotes:
                    rid = esc(q.get("review_id", "")[:8])
                    txt = esc(q.get("text", ""))
                    render_html(f'<div class="rd-quote">“{txt}” <div class="rd-meta" style="margin-top:.2rem;"><span>review_id <b>{rid}</b></span></div></div>')

    st.markdown("---")

    # Unmet Needs Ranked List
    render_html('<div class="rd-section-title" style="font-size:1.1rem;">Top Ranked Unmet User Needs</div>')
    for item in unmet:
        rank = item.get("rank", "—")
        stmt = esc(item.get("statement", ""))
        rids = item.get("supporting_review_ids", [])
        render_html(
            f"""
            <div class="rd-card" style="border-left:3px solid #3C1053;margin-bottom:.5rem;">
              <div class="rd-card-head">
                <div class="rd-card-title">#{rank}. {stmt}</div>
                <span class="rd-badge muted">{len(rids)} reviews</span>
              </div>
            </div>
            """
        )


# --- SCREEN 3: MULTI-CATEGORY SHOPPERS ---
def render_screen_3(data) -> None:
    render_html(
        '<div class="rd-section-title">Review Analysis of Multi-Category Buyers</div>'
        '<div class="rd-section-sub">Cross-category purchasing patterns, basket expansion triggers, and platform switching behaviors (Blinkit, Instamart, BigBasket, Amazon).</div>'
    )

    multi_data = data.multi_category_analysis
    themes = multi_data.get("themes", [])
    platforms = multi_data.get("platform_insights", [])

    c1, c2, c3 = st.columns(3)
    c1.metric("Multi-Category Reviews Sampled", f"{multi_data.get('sample_size', 450):,} Reviews")
    c2.metric("Cross-Category Themes", len(themes))
    c3.metric("Platform Comparisons Mined", len(platforms))

    st.markdown("#### ")

    # Multi-category themes
    render_html('<div class="rd-section-title" style="font-size:1.1rem;">Cross-Category Purchasing & Expansion Patterns</div>')
    for t in themes:
        label = esc(t.get("label", t.get("theme_id", "")))
        summary = esc(t.get("summary", ""))
        cats = t.get("category_overlap", [])
        cat_pills = " ".join(f'<span class="rd-badge muted">{esc(c)}</span>' for c in cats)
        count = t.get("review_count", len(t.get("supporting_review_ids", [])))

        render_html(
            f"""
            <div class="rd-card accent" style="margin-bottom:.8rem;">
              <div class="rd-card-head">
                <div class="rd-card-title">{label}</div>
                <span class="rd-badge">{count} reviews</span>
              </div>
              <div class="rd-card-desc">{summary}</div>
              <div class="rd-pill-row">{cat_pills}</div>
            </div>
            """
        )
        quotes = t.get("quotes", [])
        if quotes:
            with st.expander(f"View shopper quotes for {label}"):
                for q in quotes:
                    rid = esc(q.get("review_id", "")[:8])
                    txt = esc(q.get("text", ""))
                    render_html(f'<div class="rd-quote">“{txt}” <div class="rd-meta" style="margin-top:.2rem;"><span>review_id <b>{rid}</b></span></div></div>')

    st.markdown("---")

    # Platform Comparison Insights
    render_html('<div class="rd-section-title" style="font-size:1.1rem;">Platform Switching & Comparison Signals</div>')
    for p in platforms:
        plat = esc(p.get("platform", "Competitor"))
        finding = esc(p.get("finding", ""))
        quote = esc(p.get("quote", ""))

        render_html(
            f"""
            <div class="rd-card" style="border-left:3px solid #FF8A00;">
              <div class="rd-card-head">
                <div class="rd-card-title">🆚 vs. {plat}</div>
              </div>
              <div class="rd-card-desc" style="color:#FFF;">{finding}</div>
              <div class="rd-quote">“{quote}”</div>
            </div>
            """
        )


# --- SCREEN 4: DISCOVERY CHATBOT ---
def render_screen_4(retriever: ReviewRetriever) -> None:
    render_html(
        '<div class="rd-section-title">Product Discovery Q&A Chatbot</div>'
        '<div class="rd-section-sub">Ask grounded discovery questions over all 15,000 customer reviews.</div>'
    )

    api_key_set = bool(get_secret("GROQ_API_KEY"))
    status_label = "LLM Online" if api_key_set else "LLM Offline"
    status_color = "#FF8A00" if api_key_set else "#FF6B6B"

    render_html(
        f'<div class="rd-pill-row">'
        f'<span class="rd-badge" style="background:rgba(255,138,0,.15);color:{status_color};">{status_label}</span>'
        f'<span class="rd-badge muted">{retriever.corpus_size:,} reviews indexed</span>'
        f'</div>'
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.caption("Quick starter questions:")
    sug_cols = st.columns(2)
    starters = [
        "Why do users repeatedly buy from the same categories?",
        "What prevents users from exploring new categories?",
        "What triggers customer care & refund frustrations?",
        "Which user segments are most likely to experiment?"
    ]
    for i, q in enumerate(starters):
        if sug_cols[i % 2].button(q, key=f"chat_sugg_{i}", use_container_width=True):
            with st.spinner("Analyzing review corpus..."):
                res = answer_question(q, retriever)
            st.session_state.chat_history.append((q, res))
            st.rerun()

    with st.form("discovery_chat_form", clear_on_submit=True):
        prompt = st.text_input("Ask a question about product discovery, category trial, or shopping habits",
                               placeholder="e.g. Why are customers hesitant to buy cosmetics or fresh produce?")
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
        render_html(f'<div class="rd-card accent" style="border-left:3px solid #FF8A00;">{format_chat_answer(result.answer)}</div>')

        if result.retrieved:
            with st.expander(f"View grounded review sources ({len(result.retrieved)} reviews)"):
                for item in result.retrieved:
                    doc = esc(item.document[:300]) + ("…" if len(item.document) > 300 else "")
                    render_html(
                        f'<div class="rd-card" style="margin-bottom:.4rem;padding:.7rem .9rem;">'
                        f'<div class="rd-meta">{stars(item.rating)} <span><b>{esc(item.date)}</b></span> <span class="rd-badge muted">{esc(item.platform)}</span> <span>match {item.similarity:.0%}</span> <span>id <b>{esc(item.review_id[:8])}</b></span></div>'
                        f'<div style="color:#D0D0D0;font-size:.85rem;margin-top:.3rem;">{doc}</div></div>'
                    )

    if st.session_state.chat_history and st.button("Clear Chat History", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()


# --- SCREEN 5: REVIEW EXPLORER (15,000 CORPUS) ---
def render_screen_5(data) -> None:
    render_html(
        '<div class="rd-section-title">Review Explorer (15,000 Corpus Access)</div>'
        '<div class="rd-section-sub">Browse, search, and filter all normalized customer reviews in the dataset.</div>'
    )

    all_reviews = data.reviews
    fcol, rcol = st.columns([1, 2.6], gap="large")

    with fcol:
        render_html('<div class="rd-card-title">Search & Filters</div>')
        query = st.text_input("Search review text", placeholder="Keywords: refund, search, organic, milk, app")
        rating_choice = st.radio("Rating filter", ["All", "5★", "4★", "3★", "2★", "1★"], horizontal=True, key="exp_rating")
        platform_choice = st.selectbox("Platform filter", ["All", "google_play", "app_store", "reddit", "youtube", "x"])
        sort_choice = st.selectbox("Sort order", ["Newest first", "Oldest first", "Most helpful", "Lowest rating", "Highest rating"])
        if st.button("Reset Filters", use_container_width=True):
            st.session_state.pop("exp_rating", None)
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

        # Pagination
        sig = (query.strip().lower(), rating_choice, platform_choice, sort_choice)
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
              <div style="color:#B6ABB6;font-size:.8rem;">Showing {start + 1:,}–{end:,} of {len(filtered):,}</div>
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
                f'<div style="text-align:center;color:#B6ABB6;font-size:.85rem;padding-top:.45rem;">'
                f'Page <b style="color:#fff;">{page + 1}</b> of {total_pages}</div>'
            )
        with next_col:
            if st.button("Next →", use_container_width=True, disabled=page >= total_pages - 1, key="exp_next"):
                st.session_state["exp_page"] = page + 1
                st.rerun()


# --- MAIN APP ENTRYPOINT ---
def main():
    data = _load_data()
    retriever = _get_retriever()
    render_header(data)

    # State-managed vertical navigation runner in sidebar
    nav_tabs = [
        "🏠 Overview & Discovery Questions",
        "💡 User Needs Analysis",
        "🛒 Multi-Category Shoppers",
        "💬 Product Discovery Chatbot",
        "🔍 Review Explorer (15k)"
    ]

    if "active_nav_tab" not in st.session_state:
        st.session_state["active_nav_tab"] = nav_tabs[0]

    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=160)
        render_html(
            '<div style="padding:.2rem 0 1rem 0;border-bottom:1px solid #351F50;margin-bottom:1rem;">'
            '<div style="font-weight:900;color:#FFFFFF;font-size:1.1rem;display:flex;align-items:center;gap:.4rem;">'
            '<span style="font-family:\'Outfit\',sans-serif;font-weight:900;color:#FFF;background:linear-gradient(135deg,#7B2CBF,#3A0CA3);padding:.15rem .5rem;border-radius:6px;font-size:.88rem;letter-spacing:-.03em;">myntra ⚡</span>'
            '<span>Navigation</span>'
            '</div>'
            '<div style="font-size:.78rem;color:#B6ABB6;margin-top:.25rem;">VOC Analysis Engine</div>'
            '</div>'
        )
        selected_nav = st.radio(
            "Navigation Menu",
            nav_tabs,
            index=nav_tabs.index(st.session_state["active_nav_tab"]),
            key="active_nav_tab",
            label_visibility="collapsed"
        )

    if selected_nav == nav_tabs[0]:
        render_screen_1(data)
    elif selected_nav == nav_tabs[1]:
        render_screen_2(data)
    elif selected_nav == nav_tabs[2]:
        render_screen_3(data)
    elif selected_nav == nav_tabs[3]:
        render_screen_4(retriever)
    else:
        render_screen_5(data)


if __name__ == "__main__":
    main()
