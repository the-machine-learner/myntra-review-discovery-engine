"""Myntra-inspired design system: global CSS + reusable HTML card helpers.
Ported near-verbatim from reference/app — fully domain-agnostic (visual
styling only, no grocery-specific copy).

All review cards are grounded in non-PII fields only (review_id, rating, date,
app_version, thumbs_up).
"""

from __future__ import annotations

import html
import re
from datetime import date

import streamlit as st

_CITATION_RE = re.compile(r"\[\s*review_id\s*:\s*([a-zA-Z0-9_:-]+)\s*\]")

MYNTRA_PURPLE = "#3C1053"
MYNTRA_PURPLE_LIGHT = "#5C1D80"
MYNTRA_ORANGE = "#FF8A00"
BG = "#0C0614"
CARD_BG = "#1B1028"
CARD_BG_HOVER = "#28183C"
BORDER = "#351F50"
TEXT = "#FFFFFF"
TEXT_MUTED = "#B6ABB6"

_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&display=swap');

html, body, [class*="css"], .stApp, button, input, textarea, select {
    font-family: 'Outfit', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
}

.stApp { background-color: #0C0614; }

/* Hide default Streamlit chrome & deploy button for a cleaner product look */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"], .stDeployButton { display: none !important; visibility: hidden !important; }
.block-container { padding-top: 1.5rem !important; padding-bottom: 3rem !important; max-width: 1200px; }

/* Entry animation */
@keyframes fadeUp { 0% { opacity: 0; transform: translateY(16px); } 100% { opacity: 1; transform: translateY(0); } }
@keyframes pop { 0% { opacity: 0; transform: scale(.97); } 100% { opacity: 1; transform: scale(1); } }
.block-container > div { animation: fadeUp .5s cubic-bezier(.2,.8,.2,1); }

h1, h2, h3, h4, h5, h6 { color: #FFFFFF !important; font-weight: 800 !important; letter-spacing: -.02em !important; }

/* Tabs -> Myntra Purple Pills */
.stTabs [data-baseweb="tab-list"] { gap: .5rem; border-bottom: none; background: transparent; }
.stTabs [data-baseweb="tab"] {
    background: #1B1028 !important; border-radius: 500px !important; padding: .45rem 1.25rem !important;
    color: #B6ABB6 !important; font-weight: 700 !important; font-size: .85rem !important; border: none !important;
    transition: all .25s ease !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #FFFFFF !important; background: #28183C !important; }
.stTabs [aria-selected="true"] { background: #3C1053 !important; color: #FFFFFF !important; border: 1px solid #FF8A00 !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none !important; }

/* Buttons -> Orange pills */
.stButton > button {
    border-radius: 500px !important; font-weight: 700 !important; letter-spacing: .04em !important;
    border: none !important; background: #FF8A00 !important; color: #FFFFFF !important;
    padding: .5rem 1.5rem !important; transition: all .2s ease !important;
}
.stButton > button:hover { transform: scale(1.04); background: #FFA233 !important; color: #FFFFFF !important; }
.stButton > button:focus { box-shadow: none !important; color: #FFFFFF !important; }

/* Inputs */
input, textarea, div[data-baseweb="input"] input, [data-testid="stChatInput"] textarea {
    background: #28183C !important; color: #FFFFFF !important; border-radius: 8px !important; border: 1px solid transparent !important;
}
div[data-baseweb="select"] > div, div[data-baseweb="input"] {
    background: #28183C !important; border-radius: 8px !important; border: 1px solid transparent !important; color: #fff !important;
}
div[data-baseweb="select"]:hover > div { border-color: #FF8A00 !important; }
label, .stRadio label, .stSelectbox label { color: #B6ABB6 !important; font-weight: 600 !important; }

/* Radio navigation chips */
.stRadio [role="radiogroup"] { gap: .5rem; flex-wrap: wrap; margin-bottom: 1.2rem; }
.stRadio [role="radiogroup"] label {
    background: #1B1028 !important; border-radius: 500px !important; padding: .45rem 1.25rem !important;
    color: #B6ABB6 !important; font-weight: 700 !important; font-size: .88rem !important; border: 1px solid #351F50 !important;
    transition: all .25s ease !important; cursor: pointer; display: inline-flex !important; align-items: center !important;
}
.stRadio [role="radiogroup"] label:hover { color: #FFFFFF !important; background: #28183C !important; }
.stRadio [role="radiogroup"] label:has(input:checked) { background: #3C1053 !important; color: #FFFFFF !important; border: 1px solid #FF8A00 !important; }
.stRadio [role="radiogroup"] input { display: none !important; }

/* Sidebar Vertical Navigation Runner */
[data-testid="stSidebar"] {
    background-color: #140C20 !important;
    border-right: 1px solid #351F50 !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
    color: #FFFFFF !important;
    font-size: 1.1rem !important;
    letter-spacing: -.01em !important;
}
[data-testid="stSidebar"] .stRadio [role="radiogroup"] {
    display: flex !important;
    flex-direction: column !important;
    gap: .55rem !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label {
    display: flex !important;
    width: 100% !important;
    border-radius: 12px !important;
    padding: .75rem 1rem !important;
    background: #1B1028 !important;
    border: 1px solid #351F50 !important;
    color: #B6ABB6 !important;
    font-weight: 700 !important;
    font-size: .88rem !important;
    transition: all .2s ease !important;
}
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover {
    background: #28183C !important;
    color: #FFFFFF !important;
    border-color: #5C1D80 !important;
}
/* Parent Container Expansion & Alignment for stExpandSidebarButton */
.st-emotion-cache-70qvj9,
.st-emotion-cache-8ezv7j,
.e3g0k5y5,
.e3g0k5y3,
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {
    width: auto !important;
    height: auto !important;
    min-width: 52px !important;
    min-height: 52px !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    overflow: visible !important;
}

/* Compact Sleek Sidebar Toggle Button (stSidebarCollapseButton) */
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="collapsedControl"] button,
[data-testid="stSidebarHeader"] button,
button[aria-label="Collapse sidebar"],
button[aria-label="Expand sidebar"] {
    width: 34px !important;
    height: 34px !important;
    min-width: 34px !important;
    min-height: 34px !important;
    background: #28183C !important;
    border: 1.5px solid #FF8A00 !important;
    border-radius: 8px !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 10px rgba(255, 138, 0, 0.4) !important;
    transition: all .2s ease-in-out !important;
    cursor: pointer !important;
    margin: 0 !important;
    padding: 0 !important;
    opacity: 1 !important;
    visibility: visible !important;
}

[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="stExpandSidebarButton"]:hover,
[data-testid="stSidebarCollapsedControl"] button:hover,
[data-testid="collapsedControl"] button:hover,
[data-testid="stSidebarHeader"] button:hover {
    background: #3C1053 !important;
    border-color: #FFA233 !important;
    transform: scale(1.06) !important;
    box-shadow: 0 4px 14px rgba(255, 138, 0, 0.6) !important;
}

/* Inner Span & Material Icon Centering */
[data-testid="stSidebarCollapseButton"] button *,
[data-testid="stExpandSidebarButton"] span,
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"],
[data-testid="stSidebarCollapsedControl"] button *,
[data-testid="collapsedControl"] button *,
.st-emotion-cache-189uypx,
.st-emotion-cache-ujm5ma {
    font-size: 1.25rem !important;
    font-weight: 700 !important;
    color: #FFFFFF !important;
    fill: #FFFFFF !important;
    stroke: #FFFFFF !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    line-height: 1 !important;
    width: auto !important;
    height: auto !important;
    opacity: 1 !important;
}

/* Metrics */
[data-testid="stMetric"] {
    background: #1B1028; border: 1px solid #351F50; border-radius: 12px; padding: 1.1rem 1.25rem;
    transition: border-color .25s ease, transform .25s ease;
}
[data-testid="stMetric"]:hover { border-color: #FF8A00; transform: translateY(-2px); }
[data-testid="stMetricValue"] { font-weight: 800 !important; font-size: 2.2rem !important; color: #FFFFFF !important; }
[data-testid="stMetricLabel"] { color: #B6ABB6 !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: .06em; font-size: .72rem !important; }

/* Chat */
.stChatMessage { background: #1B1028 !important; border: 1px solid #351F50 !important; border-radius: 14px !important; animation: pop .35s ease; }

/* Expander */
[data-testid="stExpander"] { border: 1px solid #351F50 !important; border-radius: 12px !important; background: #140C20 !important; }
.streamlit-expanderHeader, [data-testid="stExpander"] summary { color: #FFFFFF !important; font-weight: 600 !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid #351F50 !important; border-radius: 12px !important; overflow: hidden; }

/* Blockquote */
blockquote { border-left: 4px solid #FF8A00 !important; padding: .25rem 0 .25rem 1rem !important; color: #B6ABB6 !important; font-style: italic; margin: .75rem 0 !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #28183C; border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: #3c245c; }

/* ---- Responsive / mobile ---- */
@media (max-width: 768px) {
    .block-container { padding-left: .8rem !important; padding-right: .8rem !important; padding-top: 1rem !important; }
    .stTabs [data-baseweb="tab-list"] { overflow-x: auto; flex-wrap: nowrap; -webkit-overflow-scrolling: touch; padding-bottom: .35rem; }
    .stTabs [data-baseweb="tab"] { flex: 0 0 auto; font-size: .78rem !important; padding: .4rem 1rem !important; }
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
    .rd-card { padding: .9rem 1rem; }
    .rd-card-title { font-size: .96rem; }
    .rd-section-title { font-size: 1.05rem; }
}
@media (max-width: 480px) {
    [data-testid="stMetricValue"] { font-size: 1.35rem !important; }
    .rd-meta { gap: .6rem; font-size: .72rem; }
}

/* ---- custom card primitives ---- */
.rd-card {
    background: #1B1028; border: 1px solid #351F50; border-radius: 14px; padding: 1.1rem 1.25rem;
    margin-bottom: .85rem; transition: background .25s ease, border-color .25s ease, transform .25s ease;
    animation: fadeUp .45s cubic-bezier(.2,.8,.2,1);
}
.rd-card:hover { background: #28183C; border-color: #5C1D80; transform: translateY(-2px); }
.rd-card.accent { border-left: 3px solid #FF8A00; }

.rd-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: .5rem; }
.rd-card-title { color: #FFFFFF; font-weight: 700; font-size: 1.02rem; line-height: 1.35; margin: 0; }
.rd-card-desc { color: #B6ABB6; font-size: .9rem; line-height: 1.5; margin: .25rem 0 .6rem 0; }

.rd-badge { display: inline-flex; align-items: center; gap: .35rem; background: rgba(255,138,0,.14); color: #FF8A00;
    font-size: .68rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; padding: .25rem .6rem; border-radius: 500px; white-space: nowrap; }
.rd-badge.warn { background: rgba(244,180,0,.14); color: #F2C744; }
.rd-badge.neg { background: rgba(226,33,52,.16); color: #FF6B6B; }
.rd-badge.muted { background: #28183C; color: #B6ABB6; }

.rd-meta { display: flex; flex-wrap: wrap; gap: .9rem; color: #6f5f84; font-size: .76rem; font-weight: 600; letter-spacing: .02em; }
.rd-meta b { color: #B6ABB6; font-weight: 700; }
.rd-stars { color: #FF8A00; letter-spacing: 1px; }
.rd-stars .off { color: #432b58; }

.rd-section-title { color: #FFFFFF; font-weight: 800; font-size: 1.15rem; letter-spacing: -.02em; margin: .2rem 0 .15rem 0; }
.rd-section-sub { color: #B6ABB6; font-size: .85rem; margin: 0 0 .9rem 0; }

.rd-quote { border-left: 3px solid #FF8A00; padding: .1rem 0 .1rem .9rem; color: #E0D7E8; font-style: italic; font-size: .9rem; margin: .5rem 0; }

.rd-pill-row { display: flex; flex-wrap: wrap; gap: .4rem; margin: .2rem 0 .6rem 0; }

/* ---- Chat answer: bold insights, de-emphasised inline citations ---- */
.rd-answer { color: #FFFFFF; font-size: 1.05rem; font-weight: 600; line-height: 1.7;
    letter-spacing: -.005em; white-space: pre-wrap; }
.rd-answer .rd-cite {
    display: inline-block; font-size: .62rem; font-weight: 700; line-height: 1;
    color: #FF8A00; background: #241438; border: 1px solid #43266A; border-radius: 500px;
    padding: .12rem .42rem; margin: 0 .12rem; vertical-align: middle; letter-spacing: .03em;
    white-space: nowrap; }
@media (max-width: 480px) { .rd-answer { font-size: .98rem; } }
/* ---- Myntra Orange Refresh Pipeline Button & Status Badge ---- */
.stButton > button {
    background: linear-gradient(135deg, #FF8A00, #E07B00) !important;
    color: #FFFFFF !important;
    border-radius: 500px !important;
    font-weight: 800 !important;
    font-size: 0.81rem !important;
    padding: .35rem 1.05rem !important;
    border: none !important;
    box-shadow: 0 4px 12px rgba(255, 138, 0, 0.35) !important;
    transition: all .2s ease-in-out !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #FFA233, #FF8A00) !important;
    color: #FFFFFF !important;
    transform: scale(1.04) !important;
    box-shadow: 0 6px 18px rgba(255, 138, 0, 0.6) !important;
}
.pipeline-status-badge {
    background: #06371B;
    border: 1px solid #0E5C2E;
    border-radius: 500px;
    padding: .18rem .7rem;
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    line-height: 1.2;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.15);
}
.pipeline-status-dot {
    width: 7px;
    height: 7px;
    background-color: #10B981;
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 6px #10B981;
}
.pipeline-status-text {
    color: #10B981;
    font-weight: 800;
    font-size: .78rem;
    letter-spacing: -.01em;
}
</style>
"""


def inject_global_css() -> None:
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def esc(text: str) -> str:
    return html.escape(str(text or ""))


def week_label(iso_week_str: str) -> str:
    """Convert '2026-W15' to a readable 'Apr 06' (week-start date)."""
    try:
        year, week = iso_week_str.split("-W")
        return date.fromisocalendar(int(year), int(week), 1).strftime("%b %d")
    except (ValueError, AttributeError):
        return iso_week_str


def stars(rating: int) -> str:
    rating = max(0, min(5, int(rating or 0)))
    on = "★" * rating
    off = f'<span class="off">{"★" * (5 - rating)}</span>'
    return f'<span class="rd-stars">{on}{off}</span>'


def rating_badge_class(rating: int) -> str:
    if rating <= 2:
        return "neg"
    if rating == 3:
        return "warn"
    return ""


def review_card(*, review_id: str, rating: int, date: str, app_version: str,
                body: str, platform: str = "google_play", thumbs_up: int = 0, similarity: float | None = None,
                max_chars: int = 360) -> str:
    text = esc(body)
    if len(body or "") > max_chars:
        text = esc(body[:max_chars].rsplit(" ", 1)[0]) + "…"

    meta_bits = [f"<span><b>{esc(date)}</b></span>"]
    meta_bits.append(f"<span class='rd-badge muted'>{esc(platform)}</span>")
    if app_version:
        meta_bits.append(f"<span>v{esc(app_version)}</span>")
    if thumbs_up:
        meta_bits.append(f"<span>👍 {int(thumbs_up)}</span>")
    if similarity is not None:
        meta_bits.append(f"<span>match {similarity:.0%}</span>")
    meta_bits.append(f"<span>id <b>{esc(review_id[:8])}</b></span>")

    return f"""
    <div class="rd-card">
      <div class="rd-card-head">
        <div class="rd-meta">{stars(rating)}</div>
      </div>
      <div class="rd-card-desc" style="color:#E0E0E0;">{text}</div>
      <div class="rd-meta">{''.join(meta_bits)}</div>
    </div>
    """


def format_chat_answer(answer: str) -> str:
    """Render a grounded answer with prominent insight text and small, de-emphasised
    [review_id: ...] citations shown as compact id pills."""
    escaped = esc(answer)

    def _cite(match: re.Match) -> str:
        rid = match.group(1)
        return f'<span class="rd-cite">id {esc(rid[:8])}</span>'

    body = _CITATION_RE.sub(_cite, escaped)
    return f'<div class="rd-answer">{body}</div>'


def render_html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)
