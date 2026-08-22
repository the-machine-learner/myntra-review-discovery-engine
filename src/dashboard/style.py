"""Myntra-inspired design system: global CSS + reusable HTML card helpers.

Light theme, colors sampled directly from the Myntra logo (Myntra_logo_PNG_(2).png):
pink #F41CB2, orange #F25511, near-black #231F20 for text.

All review cards are grounded in non-PII fields only (review_id, rating, date,
app_version, thumbs_up).
"""

from __future__ import annotations

import html
import re
from datetime import date

import streamlit as st

_CITATION_RE = re.compile(r"\[\s*review_id\s*:\s*([a-zA-Z0-9_:-]+)\s*\]")

MYNTRA_PINK = "#F41CB2"
MYNTRA_PINK_LIGHT = "#FDEAF6"
MYNTRA_ORANGE = "#F2551D"
MYNTRA_ORANGE_LIGHT = "#FFF1EA"
BG = "#FFFFFF"
CARD_BG = "#FFFFFF"
CARD_BG_HOVER = "#FFF5FB"
BORDER = "#EDE2E9"
TEXT = "#231F20"
TEXT_MUTED = "#6E6470"
SIDEBAR_BG = "#FCF9FB"

_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&display=swap');

html, body, [class*="css"], .stApp, button, input, textarea, select {
    font-family: 'Outfit', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
}

.stApp { background-color: #FFFFFF; }

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

h1, h2, h3, h4, h5, h6 { color: #231F20 !important; font-weight: 800 !important; letter-spacing: -.02em !important; }

/* Chart text visibility (Altair / Vega SVG labels and legend text) */
.vega-embed text, .vega-embed .role-axis-label text, .vega-embed .role-legend-label text, .vega-embed .role-legend-title text {
    fill: #231F20 !important;
}

/* Pipeline Status Badge */
.pipeline-status-badge {
    display: inline-flex; align-items: center; gap: .4rem; background: #E6F9F0;
    border: 1px solid #1FA463; padding: .25rem .65rem; border-radius: 500px; font-size: .76rem; font-weight: 700;
}
.pipeline-status-dot {
    width: 8px; height: 8px; border-radius: 50%; background: #1FA463; box-shadow: 0 0 6px #1FA463;
}
.pipeline-status-text { color: #157344; font-weight: 700; }

/* Tabs -> Myntra Pink Pills */
.stTabs [data-baseweb="tab-list"] { gap: .5rem; border-bottom: none; background: transparent; }
.stTabs [data-baseweb="tab"] {
    background: #FFFFFF !important; border-radius: 500px !important; padding: .45rem 1.25rem !important;
    color: #F41CB2 !important; font-weight: 700 !important; font-size: .85rem !important; border: 1px solid #EDE2E9 !important;
    transition: all .25s ease !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #F41CB2 !important; background: #FFF5FB !important; border-color: #F9B8E4 !important; }
.stTabs [aria-selected="true"] { background: #F41CB2 !important; color: #FFFFFF !important; border: 1px solid #F2551D !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none !important; }

/* Buttons -> Myntra gradient pills */
.stButton > button {
    background: linear-gradient(135deg, #F2551D, #F41CB2) !important;
    color: #FFFFFF !important;
    border-radius: 500px !important;
    font-weight: 800 !important;
    letter-spacing: .04em !important;
    border: none !important;
    padding: .5rem 1.5rem !important;
    box-shadow: 0 4px 12px rgba(242, 85, 17, 0.25) !important;
    transition: all .2s ease-in-out !important;
}
.stButton > button:hover {
    transform: scale(1.04);
    box-shadow: 0 6px 18px rgba(244, 28, 178, 0.35) !important;
    color: #FFFFFF !important;
}
.stButton > button:focus { box-shadow: none !important; color: #FFFFFF !important; }

/* Inputs & Placeholders & Caret Cursor */
input, textarea, div[data-baseweb="input"] input, [data-testid="stChatInput"] textarea {
    background: #F7F2F5 !important; color: #231F20 !important; border-radius: 8px !important; border: 1px solid #EDE2E9 !important;
    caret-color: #231F20 !important;
}
input::placeholder, textarea::placeholder, [data-testid="stChatInput"] textarea::placeholder,
div[data-baseweb="input"] input::placeholder, [data-baseweb="base-input"] input::placeholder {
    color: #231F20 !important;
    opacity: 0.6 !important;
}
div[data-baseweb="select"] > div, div[data-baseweb="input"] {
    background: #F7F2F5 !important; border-radius: 8px !important; border: 1px solid #EDE2E9 !important; color: #231F20 !important;
}
div[data-baseweb="select"]:hover > div { border-color: #F2551D !important; }
label, .stRadio label, .stSelectbox label { color: #231F20 !important; font-weight: 600 !important; }

/* Radio navigation chips */
.stRadio [role="radiogroup"] { gap: .5rem; flex-wrap: wrap; margin-bottom: 1.2rem; }
.stRadio [role="radiogroup"] label {
    background: #FFFFFF !important; border-radius: 500px !important; padding: .45rem 1.25rem !important;
    color: #F41CB2 !important; font-weight: 700 !important; font-size: .88rem !important; border: 1px solid #EDE2E9 !important;
    transition: all .25s ease !important; cursor: pointer; display: inline-flex !important; align-items: center !important;
}
.stRadio [role="radiogroup"] label *,
.stRadio [role="radiogroup"] label p,
.stRadio [role="radiogroup"] label span,
.stRadio [role="radiogroup"] label div {
    color: #F41CB2 !important;
}
.stRadio [role="radiogroup"] label:hover,
.stRadio [role="radiogroup"] label:hover *,
.stRadio [role="radiogroup"] label:hover p,
.stRadio [role="radiogroup"] label:hover span {
    color: #F41CB2 !important; background: #FFF5FB !important; border-color: #F9B8E4 !important;
}
.stRadio [role="radiogroup"] label:has(input:checked) {
    background: #F41CB2 !important; color: #FFFFFF !important; border: 1px solid #F2551D !important;
}
.stRadio [role="radiogroup"] label:has(input:checked) *,
.stRadio [role="radiogroup"] label:has(input:checked) p,
.stRadio [role="radiogroup"] label:has(input:checked) span {
    color: #FFFFFF !important;
}
.stRadio [role="radiogroup"] input { display: none !important; }

/* Sidebar Vertical Navigation Runner */
[data-testid="stSidebar"] {
    background-color: #FCF9FB !important;
    border-right: 1px solid #EDE2E9 !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
    color: #231F20 !important;
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
    background: #FFFFFF !important;
    border: 1px solid #EDE2E9 !important;
    color: #F41CB2 !important;
    font-weight: 700 !important;
    font-size: .88rem !important;
    transition: all .2s ease !important;
}
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label *,
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label p,
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label span,
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label div[data-testid="stMarkdownContainer"] p {
    color: #F41CB2 !important;
}
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover,
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover *,
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover p,
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover span {
    background: #FFF5FB !important;
    color: #F41CB2 !important;
    border-color: #F9B8E4 !important;
}
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:has(input:checked) *,
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:has(input:checked) p,
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:has(input:checked) span {
    color: #FFFFFF !important;
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

/* Compact Sleek Sidebar Toggle Button (stSidebarCollapseButton) — kept as a
   solid colored chip regardless of theme so the white icon always has
   guaranteed contrast, default orange / pink on hover (both from the logo). */
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
    background: #F2551D !important;
    border: 1.5px solid #F2551D !important;
    border-radius: 8px !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 10px rgba(242, 85, 17, 0.35) !important;
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
    background: #F41CB2 !important;
    border-color: #F41CB2 !important;
    transform: scale(1.06) !important;
    box-shadow: 0 4px 14px rgba(244, 28, 178, 0.45) !important;
}

/* Inner Span & Material Icon Centering — stays white; button background is
   always a solid brand color, so contrast holds in both default and hover. */
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
    background: #FFFFFF; border: 1px solid #EDE2E9; border-radius: 12px; padding: 1.1rem 1.25rem;
    transition: border-color .25s ease, transform .25s ease;
}
[data-testid="stMetric"]:hover { border-color: #F2551D; transform: translateY(-2px); }
[data-testid="stMetricValue"] { font-weight: 800 !important; font-size: 2.2rem !important; color: #231F20 !important; }
[data-testid="stMetricLabel"] { color: #6E6470 !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: .06em; font-size: .72rem !important; }

/* Chat */
.stChatMessage { background: #FFFFFF !important; border: 1px solid #EDE2E9 !important; border-radius: 14px !important; animation: pop .35s ease; }

/* Expander */
[data-testid="stExpander"] { border: 1px solid #EDE2E9 !important; border-radius: 12px !important; background: #FCF9FB !important; }
.streamlit-expanderHeader, [data-testid="stExpander"] summary { color: #231F20 !important; font-weight: 600 !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid #EDE2E9 !important; border-radius: 12px !important; overflow: hidden; }

/* Blockquote */
blockquote { border-left: 4px solid #F2551D !important; padding: .25rem 0 .25rem 1rem !important; color: #6E6470 !important; font-style: italic; margin: .75rem 0 !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #E7DEE4; border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: #D8C7D2; }

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
    background: #FFFFFF; border: 1px solid #EDE2E9; border-radius: 14px; padding: 1.1rem 1.25rem;
    margin-bottom: .85rem; transition: background .25s ease, border-color .25s ease, transform .25s ease;
    animation: fadeUp .45s cubic-bezier(.2,.8,.2,1);
    box-shadow: 0 1px 3px rgba(35,31,32,.04);
}
.rd-card:hover { background: #FFF5FB; border-color: #F9B8E4; transform: translateY(-2px); }
.rd-card.accent { border-left: 3px solid #F2551D; }

.rd-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: .5rem; }
.rd-card-title { color: #231F20; font-weight: 700; font-size: 1.02rem; line-height: 1.35; margin: 0; }
.rd-card-desc { color: #6E6470; font-size: .9rem; line-height: 1.5; margin: .25rem 0 .6rem 0; }

.rd-badge { display: inline-flex; align-items: center; gap: .35rem; background: rgba(242,85,17,.10); color: #C23F10;
    font-size: .68rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; padding: .25rem .6rem; border-radius: 500px; white-space: nowrap; }
.rd-badge.warn { background: rgba(201,138,0,.12); color: #9C6B00; }
.rd-badge.neg { background: rgba(224,41,75,.12); color: #C81E36; }
.rd-badge.muted { background: #F3EEF1; color: #6E6470; }

.rd-meta { display: flex; flex-wrap: wrap; gap: .9rem; color: #8A7F88; font-size: .76rem; font-weight: 600; letter-spacing: .02em; }
.rd-meta b { color: #3A323C; font-weight: 700; }
.rd-stars { color: #F2551D; letter-spacing: 1px; }
.rd-stars .off { color: #E2D8DE; }

.rd-section-title { color: #231F20; font-weight: 800; font-size: 1.15rem; letter-spacing: -.02em; margin: .2rem 0 .15rem 0; }
.rd-section-sub { color: #6E6470; font-size: .85rem; margin: 0 0 .9rem 0; }

.rd-quote { border-left: 3px solid #F2551D; padding: .1rem 0 .1rem .9rem; color: #463C49; font-style: italic; font-size: .9rem; margin: .5rem 0; }

.rd-pill-row { display: flex; flex-wrap: wrap; gap: .4rem; margin: .2rem 0 .6rem 0; }

/* ---- Chat answer: bold insights, de-emphasised inline citations ---- */
.rd-answer { color: #231F20; font-size: 1.05rem; font-weight: 600; line-height: 1.7;
    letter-spacing: -.005em; white-space: pre-wrap; }
.rd-answer .rd-cite {
    display: inline-block; font-size: .62rem; font-weight: 700; line-height: 1;
    color: #C23F10; background: #FDEAF6; border: 1px solid #F9C7E8; border-radius: 500px;
    padding: .12rem .42rem; margin: 0 .12rem; vertical-align: middle; letter-spacing: .03em;
    white-space: nowrap; }
@media (max-width: 480px) { .rd-answer { font-size: .98rem; } }

.pipeline-status-badge {
    background: #E7F7EE;
    border: 1px solid #22A06B;
    border-radius: 500px;
    padding: .18rem .7rem;
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    line-height: 1.2;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.12);
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
    color: #0B8F5C;
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
      <div class="rd-card-desc" style="color:#3A323C;">{text}</div>
      <div class="rd-meta">{''.join(meta_bits)}</div>
    </div>
    """


def format_chat_answer(answer: str) -> str:
    """Render a grounded answer cleanly in Streamlit with proper markdown tables,
    formatted lists, bold text, and compact citation pills."""
    if not answer:
        return ""

    def _cite(match: re.Match) -> str:
        rid = match.group(1)
        return f'<span class="rd-cite">id {html.escape(rid[:8])}</span>'

    # Convert citations into styled pills
    processed = _CITATION_RE.sub(_cite, answer)

    # Clean up excess consecutive blank lines that Groq markdown formatting produces
    processed = re.sub(r"\n{3,}", "\n\n", processed)

    return f'<div class="rd-answer">{processed}</div>'


def render_html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)
