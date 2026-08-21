import os
from PIL import Image as PILImage
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def build_pdf():
    pdf_filename = "Myntra_Review_Discovery_Engine_Technical_Deep_Dive.pdf"

    # 1. Page Setup & Geometry
    margin = 36  # 0.5 inch margins
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=letter,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin
    )

    styles = getSampleStyleSheet()

    # Custom Color Palette — Myntra's own brand colors (src/dashboard/style.py),
    # not Zepto's forest green, since this doc describes a Myntra-specific engine.
    PRIMARY = colors.HexColor("#3C1053")     # Myntra Purple
    SECONDARY = colors.HexColor("#7B3F9E")   # Lighter Purple
    ACCENT_BG = colors.HexColor("#F6F0FA")   # Light Lavender Background
    TEXT_DARK = colors.HexColor("#1D1224")   # Dark Charcoal Text
    TEXT_MUTED = colors.HexColor("#5E5266")  # Muted Gray Text
    BORDER_COLOR = colors.HexColor("#D9C3E8")  # Soft Border Lavender
    ORANGE_ACCENT = colors.HexColor("#FF8A00")  # Myntra Orange

    # Modify Base Styles
    styles['Normal'].textColor = TEXT_DARK
    styles['Normal'].fontSize = 9.5
    styles['Normal'].leading = 13.5

    # New Custom Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.white,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#E8D9F2"),
        spaceAfter=0
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=PRIMARY,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=SECONDARY,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        spaceAfter=6
    )

    callout_style = ParagraphStyle(
        'Callout_Text',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9.5,
        leading=14,
        textColor=PRIMARY
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white
    )

    table_body_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=TEXT_DARK
    )

    table_body_bold = ParagraphStyle(
        'TableBodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11.5,
        textColor=TEXT_DARK
    )

    story = []
    page_width = doc.width  # 540 pt

    # HEADER BANNER
    header_data = [
        [Paragraph("Myntra Wishlist Discovery Engine – Technical Deep Dive", title_style)],
        [Paragraph("How 11,055 Myntra Reviews Become a Scored, Grounded Opportunity Backlog for Wishlist-to-Purchase Conversion", subtitle_style)]
    ]
    header_table = Table(header_data, colWidths=[page_width])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PRIMARY),
        ('PADDING', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 12),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # INTRO NOTICE
    intro_text = "<i>This document explains what the engine is, how it works end to end, the reasoning behind each design decision, and the technical constraints that shaped it — including the ones that broke and had to be fixed mid-build. It is written so an evaluator can verify the engineering, not just the narrative.</i>"
    intro_table = Table([[Paragraph(intro_text, body_style)]], colWidths=[page_width])
    intro_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ACCENT_BG),
        ('BORDER', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(intro_table)
    story.append(Spacer(1, 10))

    # SECTION 1
    story.append(Paragraph("1 · The Problem This Engine Solves", h1_style))
    story.append(Paragraph(
        "Myntra's wishlist is a huge, mostly-passive save pile. Before proposing anything to fix wishlist-to-purchase "
        "conversion, a PM needs to know <i>why</i> saved items don't convert — at scale, from real customer language, "
        "not anecdote. The raw material exists (public reviews across Google Play, App Store, YouTube, MouthShut, and X) "
        "but is unusable by hand, and it has a real limitation baked in: app-store reviews were never designed to explain "
        "wishlist behavior. Most reviewers are commenting on delivery, refunds, and product quality, not on why they "
        "saved something instead of buying it. This engine is built around that constraint rather than around it:",
        body_style
    ))

    bullets = [
        "<b>Volume</b>: 11,055 reviews across 4 live channels — no product team reads that manually.",
        "<b>Noise</b>: the vast majority of the corpus is generic delivery/refund/quality complaints, not wishlist narrative — only a small slice is directly on-topic, and the engine says so out loud rather than inflating it.",
        "<b>Trust</b>: any claim a PM acts on needs to be checkable against the original review, not a paraphrase."
    ]
    for b in bullets:
        story.append(Paragraph(f"• {b}", body_style))

    story.append(Paragraph(
        "The engine turns that pile into a 14-area opportunity taxonomy scored on Reach × Impact × Confidence, a "
        "5-segment breakdown of <i>why</i> people wishlist at all, and a grounded chatbot — every score and every "
        "quote traceable back to a specific review_id.",
        body_style
    ))

    # SECTION 2
    story.append(Paragraph("2 · Why Rule-Tag + Scored-Sample + LLM-Synthesize (and Not the Alternatives)", h1_style))

    rag_table_data = [
        [Paragraph("Approach", table_header_style), Paragraph("Why Not", table_header_style)],
        [Paragraph("Read reviews manually / spreadsheet tagging", table_body_bold), Paragraph("Weeks of effort; subjective; doesn't scale; zero reproducibility.", table_body_style)],
        [Paragraph("Dump all 11,055 reviews into one giant LLM prompt", table_body_bold), Paragraph("<b>Impossible on the free tier in use</b> — ~11K reviews is roughly 600K-700K input tokens, vastly over Groq's real 8,000 tokens/minute and 200,000 tokens/day caps for this account (verified live against the Groq console, not a guess). Also unauditable.", table_body_style)],
        [Paragraph("Pure keyword/regex search only", table_body_bold), Paragraph("Cheap and runs on 100% of the corpus, but noisy on its own — see §6: regex-only precision against LLM judgment ranges from 24% to 59% agreement depending on the area. It also can't write a synthesis or judge severity.", table_body_style)],
        [Paragraph("Rule-tag + Scored Sample + LLM-Synthesize (Chosen)", table_body_bold), Paragraph("Regex tags 100% of the corpus for free (Reach); a small, deliberately-scored sample per taxonomy area gets an LLM severity read and synthesis (Impact); the gap between the two becomes an honest Confidence number instead of a hidden assumption.", table_body_style)]
    ]
    rag_table = Table(rag_table_data, colWidths=[150, page_width - 150])
    rag_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SECONDARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ACCENT_BG])
    ]))
    story.append(rag_table)
    story.append(Spacer(1, 8))

    principle_text = "<b>Core principle — grounding</b>: the LLM is treated as untrusted until its output is tied back to real review_ids present in the corpus. Every synthesis quote is checked for verbatim substring match against the original review, not just plausibility. This is what prevents hallucinated opportunities and makes the Scorecard safe for a PM to act on."
    principle_table = Table([[Paragraph(principle_text, callout_style)]], colWidths=[page_width])
    principle_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F3E8FA")),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINELEFT', (0, 0), (-1, -1), 3, SECONDARY),
    ]))
    story.append(principle_table)

    # SECTION 3 - END TO END WORKFLOW
    story.append(Paragraph("3 · End-to-End Workflow & Two Processing Pathways", h1_style))
    story.append(Paragraph(
        "The system runs two pathways off the same corpus and vector index: an <b>offline batch pathway</b> that "
        "produces the Opportunity Scorecard and Wishlist Segments once per run, and an <b>online RAG pathway</b> that "
        "answers ad-hoc questions live in the dashboard.",
        body_style
    ))

    story.append(Paragraph("<b>Pathway A — Offline Opportunity Scoring</b>", h2_style))
    stage_table_data = [
        [Paragraph("Stage", table_header_style), Paragraph("What Happens", table_header_style), Paragraph("Tech / Decision", table_header_style)],
        [Paragraph("Ingest", table_body_bold), Paragraph("Pull public reviews across up to 5 channels (Google Play, App Store, YouTube, MouthShut, X), 10-week rolling lookback, merged incrementally.", table_body_style), Paragraph("google-play-scraper, custom App Store fetcher, YouTube Data API, Playwright+BeautifulSoup for MouthShut, X fetcher", table_body_style)],
        [Paragraph("Normalize", table_body_bold), Paragraph("Dedupe near-identical reviews; filter short noise (<6 words); unify schema across channels.", table_body_style), Paragraph("Deterministic Python pipeline → data/processed/normalized_reviews.json", table_body_style)],
        [Paragraph("Embed & Index", table_body_bold), Paragraph("Convert each review to a 384-dim meaning vector; store in Chroma keyed by review_id, tagged with rule-based taxonomy metadata for scoped retrieval.", table_body_style), Paragraph("Local sentence-transformers all-MiniLM-L6-v2 + Chroma DB (collection myntra_reviews)", table_body_style)],
        [Paragraph("Rule-Tag ($0)", table_body_bold), Paragraph("Regex-match all 11,055 reviews against all 14 taxonomy areas — free, runs on 100% of the corpus regardless of which areas get LLM synthesis this run.", table_body_style), Paragraph("src/analysis/taxonomy.py::classify_rule_based", table_body_style)],
        [Paragraph("Score-Sample", table_body_bold), Paragraph("Per area, rank matched reviews by keyword density + length quality + rating friction + helpfulness + a novelty bonus for not-yet-LLM-tagged reviews; take the top 40.", table_body_style), Paragraph("src/analysis/sampler.py (OPPORTUNITY_SAMPLE_CAP_PER_AREA=40)", table_body_style)],
        [Paragraph("LLM-Synthesize", table_body_bold), Paragraph("Batch the sample (20/call) to Groq for a relevance + severity judgment and a grounded synthesis paragraph; results cached by content-hash + prompt-version so repeat runs don't re-spend tokens.", table_body_style), Paragraph("Groq openai/gpt-oss-120b, temperature=0.2, JSON mode; src/analysis/tag_cache.py", table_body_style)],
        [Paragraph("Score", table_body_bold), Paragraph("Blend free Reach stats with LLM Impact/Confidence into one comparable signal_score per area; merges into existing results rather than overwriting untouched areas.", table_body_style), Paragraph("src/analysis/scoring.py → opportunity_scores.json", table_body_style)],
        [Paragraph("Validate", table_body_bold), Paragraph("Enforce PII scrubbing, 200-word synthesis cap, and verbatim quote-in-corpus checks before anything is written to disk.", table_body_style), Paragraph("src/analysis/validators.py + opportunity_run_metadata.json", table_body_style)],
    ]
    stage_table = Table(stage_table_data, colWidths=[80, 260, 200])
    stage_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ACCENT_BG])
    ]))
    story.append(stage_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("<b>Pathway B — Online Live Chat (RAG)</b>", h2_style))
    story.append(Paragraph(
        "Question → out-of-scope gate (regex refusal for anything not about Myntra/reviews) → Chroma retrieve "
        "(top_k=8 from a fetch pool of 40, MMR re-ranked with λ=0.7 for relevance/diversity balance) → similarity "
        "threshold gate (0.30) → shared daily budget gate (see §6) → Groq generate → citation validation → "
        "<b>fallback to a free retrieval-only answer on any failure at any step</b>, never a hard error shown to the user. "
        "The same pipeline can be scoped to a single opportunity area (Deep-Dive screen) by filtering on that area's tag metadata.",
        body_style
    ))

    # SECTION 4
    story.append(Paragraph("4 · What \"Rule-Tagging,\" \"Scored Sampling,\" and \"RAG\" Actually Mean (Plain Version)", h1_style))
    story.append(Paragraph(
        "<b>Rule-tagging</b> is a free, deterministic pass: does this review's text contain any of a taxonomy area's "
        "keyword phrases (e.g. \"out of stock\", \"not sure which one to buy\")? It runs on every review, costs nothing, "
        "and gives an honest reach number — but it's a proxy, not a judgment; a review can contain a keyword and still "
        "not really be about that topic.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Scored sampling</b> decides which of the (possibly thousands of) rule-matched reviews are worth an "
        "expensive LLM call: longer, more critical, more helpful, and not-yet-reviewed reviews score higher, so each "
        "LLM call is spent where it teaches the most.",
        body_style
    ))
    story.append(Paragraph(
        "<b>RAG (Retrieval-Augmented Generation)</b> is the live-chat pattern: embed the question, retrieve the "
        "handful of reviews most similar in meaning, and generate an answer using only those retrieved reviews. "
        "The LLM never answers from general internet knowledge — it answers strictly from retrieved evidence, which "
        "is what makes every claim citable.",
        body_style
    ))

    # SECTION 5
    story.append(Paragraph("5 · Why Local Embeddings, Groq for Generation — and a Real Mid-Build Model Swap", h1_style))
    story.append(Paragraph(
        "The architecture pairs a local embedding model with a hosted generation API, and that generation model "
        "changed mid-build for a documented reason worth surfacing rather than hiding:",
        body_style
    ))

    embed_table_data = [
        [Paragraph("Task", table_header_style), Paragraph("Engine Choice", table_header_style), Paragraph("Why", table_header_style)],
        [Paragraph("Embedding 11,055 reviews + each query", table_body_bold), Paragraph("Local MiniLM (384-dim)", table_body_style), Paragraph("Free, 100% offline, zero API token budget consumed, fast on CPU.", table_body_style)],
        [Paragraph("Opportunity synthesis + segmentation + chat answers", table_body_bold), Paragraph("Groq openai/gpt-oss-120b", table_body_style), Paragraph("Strong JSON-mode reasoning at interactive Groq LPU speed.", table_body_style)],
    ]
    embed_table = Table(embed_table_data, colWidths=[150, 130, 260])
    embed_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SECONDARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ACCENT_BG])
    ]))
    story.append(embed_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<b>The model swap, in order</b>: the pipeline originally targeted <b>llama-3.3-70b-versatile</b>, which Groq "
        "removed from its lineup entirely (confirmed live via a 404 model_not_found). It was replaced with "
        "<b>openai/gpt-oss-20b</b>, which then hit its real daily token ceiling mid-run and started returning "
        "escalating 429s (264s → 432s Retry-After). The fix was switching to <b>openai/gpt-oss-120b</b> — a separate, "
        "independent quota bucket on the same account, confirmed with a live test call before committing to it. "
        "Both incidents are why the client now caps any Retry-After wait at 60 seconds and fails fast and visibly "
        "instead of silently blocking for 15+ minutes, which happened once for real during development.",
        body_style
    ))

    # SECTION 6
    story.append(Paragraph("6 · Why 40 Reviews Per Area, Not the Full Corpus (The Token-Limit Math)", h1_style))
    story.append(Paragraph(
        "This is the binding engineering constraint, and the numbers below are the real ones verified against the "
        "Groq console for this account's <b>openai/gpt-oss-120b</b> and <b>openai/gpt-oss-20b</b> models (both show "
        "identical limits) — not a placeholder guess. An earlier internal budget config used 500,000 tokens/day as a "
        "guess; the real console value is 200,000, and being 2.5× too generous is exactly what let a run blow past "
        "Groq's real server-side ceiling before the tracker caught it.",
        body_style
    ))

    story.append(Paragraph("<b>The Rate Limit Numbers (verified, this Groq account):</b>", body_style))
    story.append(Paragraph("• 8,000 tokens per minute (TPM), throttled to 7,000 with local headroom", body_style))
    story.append(Paragraph("• 200,000 tokens per day (TPD)", body_style))
    story.append(Paragraph("• 30 requests per minute (RPM), 1,000 requests/day (RPD)", body_style))

    story.append(Paragraph(
        "<b>The math</b>: a typical review is ~50–60 tokens. 11,055 reviews ≈ 570,000–660,000 input tokens. That is:<br/>"
        "• ≈ <b>80× over the 8,000 tokens-per-minute ceiling</b>, and<br/>"
        "• ≈ <b>3× over the 200,000 tokens-per-day cap</b> — on a single pass, before even accounting for output tokens.",
        body_style
    ))

    story.append(Paragraph(
        "<b>The fix — per-area scored sampling + a persistent tag cache</b>: sampler.py caps each of the 14 taxonomy "
        "areas at 40 reviews (OPPORTUNITY_SAMPLE_CAP_PER_AREA), and a content-hash + prompt-version keyed cache "
        "(llm_tag_cache.json, currently ~270KB) means a review already LLM-tagged for an area is never re-spent on "
        "in a later run — the \"novelty bonus\" in the sampler actively steers new runs toward uncovered reviews. "
        "The day this document was generated, a full run cost only <b>40 Groq calls and ~131,000 tokens</b> — well "
        "inside budget. On top of that, the shared budget tracker (src/analysis/budget.py) reserves "
        "<b>25% of the daily ceiling for live chat</b> at all times, so a background batch run can never starve a "
        "user asking a question in the dashboard.",
        body_style
    ))

    # SECTION 7
    story.append(Paragraph("7 · The Trust Layer — How Hallucination Is Prevented", h1_style))
    story.append(Paragraph("LLMs can invent plausible-sounding claims. For a PM making roadmap bets, that's dangerous. The engine defends against it with a deterministic validation layer that runs on every synthesis and every chat answer:", body_style))

    trust_table_data = [
        [Paragraph("Check", table_header_style), Paragraph("Rule Enforced", table_header_style)],
        [Paragraph("Provenance", table_body_bold), Paragraph("Every synthesis quote must appear verbatim (whitespace-normalized substring match) inside the actual sampled review, not just be plausible; every chat answer must cite a review_id that was genuinely retrieved for that question.", table_body_style)],
        [Paragraph("Structural Integrity", table_body_bold), Paragraph("Synthesis capped at 200 words; at least 1 supporting quote required; malformed JSON from the model triggers a retry, not a silent skip.", table_body_style)],
        [Paragraph("Privacy", table_body_bold), Paragraph("Emails and phone numbers are regex-scrubbed from synthesis and chat answers before display (citation tokens are excluded from the scrub so review_ids survive).", table_body_style)],
        [Paragraph("Scope Enforcement", table_body_bold), Paragraph("Out-of-scope questions are refused via regex gate before ever reaching retrieval or the LLM; low-similarity questions (<0.30) fall back to a free retrieval-only answer instead of guessing.", table_body_style)],
    ]
    trust_table = Table(trust_table_data, colWidths=[130, page_width - 130])
    trust_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ACCENT_BG])
    ]))
    story.append(trust_table)

    # SECTION 8
    story.append(Paragraph("8 · The Opportunity Scorecard — Real Results Across 14 Taxonomy Areas", h1_style))
    story.append(Paragraph(
        "Every area below is scored on the same three axes: <b>Reach</b> (% of the 11,055-review corpus a free regex "
        "match hit), <b>Impact</b> (blended rating-drop + LLM-assessed severity), and <b>Confidence</b> (how much of "
        "the matched population the LLM actually reviewed, and how often it agreed the match was genuine). The ranked "
        "table below is the live opportunity_scores.json output, not illustrative numbers.",
        body_style
    ))

    theme_table_data = [
        [Paragraph("Opportunity Area", table_header_style), Paragraph("Reach", table_header_style), Paragraph("Impact", table_header_style), Paragraph("Confidence", table_header_style), Paragraph("Signal", table_header_style)],
        [Paragraph("Trust / Review Credibility Gap", table_body_bold), Paragraph("7.6% (841)", table_body_style), Paragraph("67.8", table_body_style), Paragraph("35.1", table_body_style), Paragraph("72.5", table_body_bold)],
        [Paragraph("Quality / Material Doubt", table_body_bold), Paragraph("20.7% (2,286)", table_body_style), Paragraph("51.3", table_body_style), Paragraph("40.3", table_body_style), Paragraph("68.0", table_body_bold)],
        [Paragraph("External Validation-Seeking", table_body_bold), Paragraph("2.4% (267)", table_body_style), Paragraph("40.6", table_body_style), Paragraph("40.5", table_body_style), Paragraph("64.3", table_body_bold)],
        [Paragraph("Stock / Size / Color Availability Friction", table_body_bold), Paragraph("0.1% (16)", table_body_style), Paragraph("72.0", table_body_style), Paragraph("96.3", table_body_style), Paragraph("51.6", table_body_bold)],
        [Paragraph("Delivery / COD / Payment Friction", table_body_bold), Paragraph("0.3% (37)", table_body_style), Paragraph("73.6", table_body_style), Paragraph("95.5", table_body_style), Paragraph("50.3", table_body_bold)],
        [Paragraph("Size & Fit Uncertainty", table_body_bold), Paragraph("0.5% (50)", table_body_style), Paragraph("65.4", table_body_style), Paragraph("75.3", table_body_style), Paragraph("49.2", table_body_bold)],
        [Paragraph("Return / Exchange Anxiety", table_body_bold), Paragraph("4.8% (533)", table_body_style), Paragraph("84.7", table_body_style), Paragraph("32.3", table_body_style), Paragraph("47.0", table_body_bold)],
        [Paragraph("Comparison Paralysis", table_body_bold), Paragraph("3.5% (387)", table_body_style), Paragraph("40.0", table_body_style), Paragraph("47.2", table_body_style), Paragraph("32.6", table_body_bold)],
        [Paragraph("Wishlist as Price-Drop Watch", table_body_bold), Paragraph("0.05% (6)", table_body_style), Paragraph("49.3", table_body_style), Paragraph("48.6", table_body_style), Paragraph("30.2", table_body_bold)],
    ]
    theme_table = Table(theme_table_data, colWidths=[190, 80, 60, 75, 55])
    theme_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SECONDARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ACCENT_BG])
    ]))
    story.append(theme_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Reach and Confidence deliberately pull in opposite directions here: <b>Quality/Material Doubt</b> has the "
        "2nd-highest reach (2,286 matches) but the LLM has only sampled 2.4% of it, so Confidence stays modest (40.3) "
        "— it's a high-volume area still under-verified. <b>Stock/Size/Color Friction</b> and <b>Delivery/COD/Payment "
        "Friction</b> sit at the opposite extreme: small enough (16 and 37 matches) that the LLM has reviewed nearly "
        "all of them, so Confidence is over 95 even though Reach is tiny. Four remaining MVP areas — Styling & "
        "Occasion Uncertainty, Wishlist as Bookmark/No Intent, General Price Hesitation, and the two Wishlist-as-Gift/"
        "Inspiration areas — are in the full taxonomy and scored artifact but omitted from this table for space; two "
        "of those (Styling & Occasion Uncertainty, Wishlist Bookmark-No-Intent) currently show 0 matched reviews after "
        "their keyword sets were deliberately tightened mid-build to kill false positives — see §10.",
        body_style
    ))

    # SECTION 9
    story.append(Paragraph("9 · Wishlist Usage Segments — Why People Wishlist At All", h1_style))
    story.append(Paragraph(
        "A separate, single-label LLM pass classifies wishlist-mentioning reviews into one of 5 MECE behavioral "
        "segments (plus \"unclear\"). The candidate pool is deliberately narrow — only reviews that literally say "
        "\"wishlist\" or match one of 4 wishlist-motivation taxonomy areas — because most of the corpus simply isn't "
        "commenting on wishlist behavior at all:",
        body_style
    ))
    seg_table_data = [
        [Paragraph("Segment", table_header_style), Paragraph("Count", table_header_style), Paragraph("% of Classified", table_header_style)],
        [Paragraph("Unclear / Insufficient Signal", table_body_bold), Paragraph("52", table_body_style), Paragraph("89.7%", table_body_style)],
        [Paragraph("Price-Drop Watch", table_body_bold), Paragraph("3", table_body_style), Paragraph("5.2%", table_body_style)],
        [Paragraph("Genuine Purchase Intent", table_body_bold), Paragraph("2", table_body_style), Paragraph("3.4%", table_body_style)],
        [Paragraph("Bookmark, Not Intent", table_body_bold), Paragraph("1", table_body_style), Paragraph("1.7%", table_body_style)],
        [Paragraph("Gift List / Inspiration Board", table_body_bold), Paragraph("0 / 0", table_body_style), Paragraph("0.0%", table_body_style)],
    ]
    seg_table = Table(seg_table_data, colWidths=[220, 80, 120])
    seg_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ACCENT_BG])
    ]))
    story.append(seg_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Out of a 73-review candidate pool, 58 were classified — and 89.7% of those landed in \"Unclear.\" This is "
        "reported as-is rather than smoothed over: it's the honest ceiling of what public app-store reviews can tell "
        "you about wishlist motivation. Most of this corpus is star-rating reviews about delivery, refunds, and "
        "quality — not reflective narratives about why someone saved an item instead of buying it.",
        body_style
    ))

    # SECTION 10
    story.append(Paragraph("10 · Honest Limitations", h1_style))
    lim_bullets = [
        "<b>Inferred, not measured</b>: this engine has no access to Myntra's real wishlist telemetry — every behavioral claim is inferred from review text, not verified against actual user actions.",
        "<b>High-reach areas can still be low-confidence</b>: Quality/Material Doubt (20.7% reach) has only been 2.4% LLM-sampled — treat its synthesis as directional, not exhaustive, until more of it is reviewed.",
        "<b>Regex pre-filter is noisy by design</b>: rule/LLM agreement ranges from 24.1% (Trust) to 59.3% (Quality) across areas — the free reach number is a proxy for \"worth investigating,\" not ground truth on its own.",
        "<b>Two MVP taxonomy areas currently show zero reach</b>: Styling & Occasion Uncertainty and Wishlist-as-Bookmark keyword sets were deliberately tightened mid-build after they were matching generic praise and unrelated complaints (documented inline in taxonomy.py); they now return 0 true matches, which likely means the real signal needs an LLM-only classification pass rather than a keyword pre-filter, not that the behavior doesn't exist.",
        "<b>Corpus is skewed positive</b>: 64.2% of the 11,055 reviews are 5★ and only 23.5% are 1★ — reach percentages are relative to a mostly-satisfied corpus, not a curated complaint set.",
        "<b>Reddit was evaluated and removed</b>: both direct PRAW access and two Apify no-login fallbacks proved unreliable as a 6th channel and were dropped entirely (see git history). X/Twitter ingestion code exists but returned 0 reviews in the current corpus snapshot.",
        "<b>Ephemeral vector store</b>: on an ephemeral-disk deploy target, the Chroma index would need to rebuild on cold start; this is not yet an issue since the app currently runs locally, not on a hosted platform.",
    ]
    for lb in lim_bullets:
        story.append(Paragraph(f"• {lb}", body_style))

    # SECTION 11
    story.append(Paragraph("11 · Tech Stack Summary", h1_style))
    stack_table_data = [
        [Paragraph("Layer", table_header_style), Paragraph("Technology Choice", table_header_style)],
        [Paragraph("Ingestion", table_body_bold), Paragraph("google-play-scraper, custom App Store fetcher, YouTube Data API, Playwright + BeautifulSoup for MouthShut (shuffled page-order pagination to avoid a confirmed silent-repeat bug), X fetcher", table_body_style)],
        [Paragraph("Embeddings", table_body_bold), Paragraph("sentence-transformers all-MiniLM-L6-v2 (local, 384-dim)", table_body_style)],
        [Paragraph("Vector Store", table_body_bold), Paragraph("Chroma DB, collection \"myntra_reviews\", file-persisted, keyed by review_id with taxonomy-tag metadata for scoped retrieval", table_body_style)],
        [Paragraph("Generation", table_body_bold), Paragraph("Groq openai/gpt-oss-120b (JSON mode, temperature 0.2 batch / RAG generator), shared daily budget tracker with a 25% live-chat reservation", table_body_style)],
        [Paragraph("Dashboard", table_body_bold), Paragraph("Streamlit — 5 screens: Opportunity Scorecard, Live Chat, Review Explorer, Opportunity Deep-Dive, Wishlist Segments", table_body_style)],
        [Paragraph("Deployment", table_body_bold), Paragraph("Local Streamlit run (not yet pushed to a hosted platform as of this document)", table_body_style)],
    ]
    stack_table = Table(stack_table_data, colWidths=[100, page_width - 100])
    stack_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ACCENT_BG])
    ]))
    story.append(stack_table)

    # Build Document
    doc.build(story)
    print(f"PDF successfully built: {pdf_filename}")

if __name__ == "__main__":
    build_pdf()
