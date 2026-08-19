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
    margin = 36 # 0.5 inch margins
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=letter,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Color Palette
    PRIMARY = colors.HexColor("#0D3B2E")    # Dark Forest Green
    SECONDARY = colors.HexColor("#2D6A4F")  # Medium Forest Green
    ACCENT_BG = colors.HexColor("#F0F7F4")  # Light Sage Background
    TEXT_DARK = colors.HexColor("#1D2D24")  # Dark Charcoal Text
    TEXT_MUTED = colors.HexColor("#526058") # Muted Gray Text
    BORDER_COLOR = colors.HexColor("#B7D1C4") # Soft Border Green
    ORANGE_ACCENT = colors.HexColor("#E67E22") # Subtle Warning/Accent

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
        textColor=colors.HexColor("#D1E7DD"),
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
    page_width = doc.width # 540 pt

    # HEADER BANNER
    header_data = [
        [Paragraph("Myntra Review Discovery Engine – Technical Deep Dive", title_style)],
        [Paragraph("How 15,607 Myntra Play Store & Multi-Channel Reviews Become Grounded, Queryable Product Insight", subtitle_style)]
    ]
    header_table = Table(header_data, colWidths=[page_width])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), PRIMARY),
        ('PADDING', (0,0), (-1,-1), 12),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,1), (-1,1), 12),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # INTRO NOTICE
    intro_text = "<i>This document explains what the engine is, how it works end to end, the reasoning behind each design decision, and the technical constraints that shaped it. It is written so an evaluator can verify the engineering—not just the narrative.</i>"
    intro_table = Table([[Paragraph(intro_text, body_style)]], colWidths=[page_width])
    intro_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), ACCENT_BG),
        ('BORDER', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(intro_table)
    story.append(Spacer(1, 10))

    # SECTION 1
    story.append(Paragraph("1 · The Problem This Engine Solves", h1_style))
    story.append(Paragraph(
        "Myntra's strategic goal is to increase cross-category product discovery and reduce low-margin repeat staple reliance. "
        "Before proposing a product solution, a PM needs to know what users actually struggle with—at scale, from real evidence, not anecdote. "
        "The raw material exists (tens of thousands of public reviews across App Store, Play Store, Reddit, YouTube, X) but is unusable by hand:",
        body_style
    ))
    
    bullets = [
        "<b>Volume</b>: 15,607 reviews in a 10-week window—no product team reads that manually.",
        "<b>Noise</b>: reviews mix delivery partner bugs, app crashes, billing issues, and discovery complaints in no order.",
        "<b>Trust</b>: any manual summary a human writes is hard to verify against the original customer source."
    ]
    for b in bullets:
        story.append(Paragraph(f"• {b}", body_style))
    
    story.append(Paragraph(
        "The engine turns that pile into 4 ranked discovery-friction themes, 6 behavioral customer segments, and a grounded chatbot that answers product questions, with every answer traceable back to specific review IDs.",
        body_style
    ))

    # SECTION 2
    story.append(Paragraph("2 · Why a RAG Architecture (and Not the Alternatives)", h1_style))
    
    rag_table_data = [
        [Paragraph("Approach", table_header_style), Paragraph("Why Not", table_header_style)],
        [Paragraph("Read reviews manually / spreadsheet tagging", table_body_bold), Paragraph("Weeks of effort; subjective; doesn't scale; zero reproducibility.", table_body_style)],
        [Paragraph("Dump all reviews into one giant LLM prompt", table_body_bold), Paragraph("<b>Impossible</b>—15.6K reviews (~900K tokens) vastly exceed free-tier API rate limits (12K tokens/min). Also expensive and unauditable.", table_body_style)],
        [Paragraph("Pure keyword search / regex", table_body_bold), Paragraph("Misses semantic intent—'received expired curd' and 'best before date missing' never match on exact regex keywords but are the same complaint.", table_body_style)],
        [Paragraph("RAG + Stratified Sampling (Chosen)", table_body_bold), Paragraph("Embeds reviews by semantic meaning, retrieves only relevant reviews per query, and grounds the LLM's answer in real text—scalable, cheap, and auditable.", table_body_style)]
    ]
    rag_table = Table(rag_table_data, colWidths=[150, page_width - 150])
    rag_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), SECONDARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ACCENT_BG])
    ]))
    story.append(rag_table)
    story.append(Spacer(1, 8))

    # Core Principle Callout
    principle_text = "<b>Core principle — grounding</b>: the LLM is treated as untrusted until its output is tied back to real review_ids. This is what prevents hallucinated insights and makes the engine safe for a PM to act on."
    principle_table = Table([[Paragraph(principle_text, callout_style)]], colWidths=[page_width])
    principle_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#E8F5E9")),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LINELEFT', (0,0), (-1,-1), 3, SECONDARY),
    ]))
    story.append(principle_table)

    # SECTION 3 - END TO END WORKFLOW
    story.append(Paragraph("3 · End-to-End Workflow & Architecture Diagram", h1_style))
    story.append(Paragraph("The system is architected into two parallel processing pathways (Offline Pre-Computed Batch Analysis vs. Online Real-Time RAG):", body_style))

    # Embed User's Architecture Diagram Image
    img_path = "architecture_diagram.png"
    if os.path.exists(img_path):
        im = PILImage.open(img_path)
        w, h = im.size
        aspect = h / float(w)
        target_w = page_width
        target_h = target_w * aspect
        # Make sure image height is controlled
        if target_h > 350:
            target_h = 350
            target_w = target_h / aspect
        story.append(Spacer(1, 4))
        story.append(Image(img_path, width=target_w, height=target_h))
        story.append(Spacer(1, 8))

    # Stage by Stage Detail Table
    story.append(Paragraph("<b>Stage-by-Stage Implementation Detail</b>", h2_style))
    stage_table_data = [
        [Paragraph("Stage", table_header_style), Paragraph("What Happens", table_header_style), Paragraph("Tech / Decision", table_header_style)],
        [Paragraph("Ingest", table_body_bold), Paragraph("Pull public reviews across 5 channels (Google Play, App Store, YouTube, Reddit, X), 10-week window.", table_body_style), Paragraph("google-play-scraper, PRAW, YouTube API (Plain Python codebase)", table_body_style)],
        [Paragraph("Normalize", table_body_bold), Paragraph("Dedupe near-identical reviews; filter short noise (<6 words); strip PII (emails, numbers); unify schema.", table_body_style), Paragraph("Deterministic Python pipeline (data/processed/normalized_reviews.json)", table_body_style)],
        [Paragraph("Embed & Index", table_body_bold), Paragraph("Convert each review to a 384-dim meaning vector; store in persistent vector store keyed by review_id.", table_body_style), Paragraph("Local sentence-transformers all-MiniLM-L6-v2 + Chroma DB", table_body_style)],
        [Paragraph("Analyze (Batch)", table_body_bold), Paragraph("Sample representative 450 reviews across rating × week cells; execute 3 offline pipelines (Segmentation, Grievances, Multi-Category).", table_body_style), Paragraph("sampler.py + Groq batch processing (ANALYSIS_BATCH_SIZE=20)", table_body_style)],
        [Paragraph("Retrieve (RAG)", table_body_bold), Paragraph("For ad-hoc questions, embed query and pull top matching reviews using Cosine distance + MMR reranking.", table_body_style), Paragraph("Chroma DB similarity search (top_k=8, candidate pool k=40, lambda=0.7)", table_body_style)],
        [Paragraph("Generate (RAG)", table_body_bold), Paragraph("LLM writes grounded answer using ONLY retrieved reviews; cites review_ids; refuses off-scope.", table_body_style), Paragraph("Groq llama-3.3-70b-versatile (temperature=0.1)", table_body_style)],
        [Paragraph("Validate", table_body_bold), Paragraph("Enforce theme caps, review_id provenance checks, and PII blocking before surfacing to UI.", table_body_style), Paragraph("Deterministic validator (validators.py & run_metadata.json)", table_body_style)],
        [Paragraph("Surface", table_body_bold), Paragraph("5 interactive dashboard screens: Overview, User Needs, Multi-Category, RAG Chatbot, Review Explorer.", table_body_style), Paragraph("Streamlit app deployed to Community Cloud", table_body_style)]
    ]
    stage_table = Table(stage_table_data, colWidths=[90, 260, 190])
    stage_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ACCENT_BG])
    ]))
    story.append(stage_table)

    # SECTION 4
    story.append(Paragraph("4 · What 'Embedding' and 'RAG' Actually Mean (Plain Version)", h1_style))
    story.append(Paragraph(
        "<b>Embedding</b> converts each review into a list of 384 numbers (a vector) that captures its semantic meaning. "
        "Reviews with similar meaning end up close together in vector space, even if they share no words. "
        "That's why 'received expired curd' and 'best before date missing' cluster together automatically.",
        body_style
    ))
    story.append(Paragraph(
        "<b>RAG (Retrieval-Augmented Generation)</b> is a two-step pattern: retrieve the handful of reviews most relevant to a specific user question, "
        "then generate an answer using only those retrieved reviews. The LLM never answers from general internet knowledge—it answers strictly from retrieved evidence, which makes every claim citable.",
        body_style
    ))

    # SECTION 5
    story.append(Paragraph("5 · Why Local Embeddings, Groq for Generation", h1_style))
    story.append(Paragraph(
        "The architecture evaluates local models vs hosted endpoints. The system uses a local SentenceTransformer model paired with Groq Cloud API for generation:",
        body_style
    ))

    embed_table_data = [
        [Paragraph("Task", table_header_style), Paragraph("Engine Chosen", table_header_style), Paragraph("Why", table_header_style)],
        [Paragraph("Embedding 15,607 reviews + each query", table_body_bold), Paragraph("Local MiniLM (384-dim)", table_body_style), Paragraph("Free, 100% offline, zero API token budget consumed, runs fast on CPU.", table_body_style)],
        [Paragraph("Theme analysis + chatbot answers", table_body_bold), Paragraph("Groq llama-3.3-70b", table_body_style), Paragraph("Strong strategic reasoning; Groq's LPU speed makes responses interactive (<1s).", table_body_style)]
    ]
    embed_table = Table(embed_table_data, colWidths=[140, 130, 270])
    embed_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), SECONDARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ACCENT_BG])
    ]))
    story.append(embed_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Net effect</b>: zero embedding tokens consumed, so the entire scarce Groq token budget is reserved for generation.", body_style))

    # SECTION 6
    story.append(Paragraph("6 · Why 450 Reviews in Analysis, Not All 15,607 (The Token-Limit Math)", h1_style))
    story.append(Paragraph(
        "This is the most important engineering constraint, and a common evaluator question. The limit is not the model's context window—llama-3.3-70b has a large 128K-token context window. "
        "The binding constraint is <b>Groq's free-tier throughput cap</b>:",
        body_style
    ))

    story.append(Paragraph("<b>The Rate Limit Numbers (Groq Free Tier):</b>", body_style))
    story.append(Paragraph("• 12,000 tokens per minute (TPM)", body_style))
    story.append(Paragraph("• 100,000 tokens per day (TPD)", body_style))
    story.append(Paragraph("• 30 requests per minute (RPM), 1,000 requests/day", body_style))

    story.append(Paragraph(
        "<b>The math</b>: a typical review is ~50–60 tokens. 15,607 reviews ≈ 850,000–950,000 input tokens. That is:<br/>"
        "• ≈ <b>75× over the 12,000 tokens-per-minute ceiling</b>, and<br/>"
        "• ≈ <b>9× over the 100,000 tokens-per-day cap</b>.",
        body_style
    ))

    story.append(Paragraph(
        "<b>The fix — stratified sampling</b>: Instead of passing all 15.6K reviews, sampler.py selects a 450-review representative sample, "
        "bucketed by rating tier × ISO week, deliberately oversampling negative reviews (1–2★) because that's where actionable discovery complaints concentrate. "
        "450 reviews ≈ 22K tokens—comfortably runnable within limits. Crucially, <b>the chatbot still retrieves over all 15,607 reviews</b> in real-time.",
        body_style
    ))

    # SECTION 7
    story.append(Paragraph("7 · The Trust Layer — How Hallucination Is Prevented", h1_style))
    story.append(Paragraph("LLMs can invent plausible-sounding claims. For a PM making roadmap bets, that's dangerous. The engine defends against it with a deterministic validation layer:", body_style))

    trust_table_data = [
        [Paragraph("Check", table_header_style), Paragraph("Rule Enforced", table_header_style)],
        [Paragraph("Provenance", table_body_bold), Paragraph("Every theme and chatbot claim must cite real review_id(s) present in the corpus.", table_body_style)],
        [Paragraph("Structural Integrity", table_body_bold), Paragraph("≤4 friction clusters; off-topic noise routed to a general bucket.", table_body_style)],
        [Paragraph("Privacy", table_body_bold), Paragraph("No usernames, emails, or phone numbers ever appear in UI output.", table_body_style)],
        [Paragraph("Scope Enforcement", table_body_bold), Paragraph("Out-of-scope questions are refused rather than answered from general knowledge.", table_body_style)]
    ]
    trust_table = Table(trust_table_data, colWidths=[130, page_width - 130])
    trust_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ACCENT_BG])
    ]))
    story.append(trust_table)

    # SECTION 8
    story.append(Paragraph("8 · Core Grievance Themes Surfaced", h1_style))
    
    theme_table_data = [
        [Paragraph("Theme", table_header_style), Paragraph("Reviews", table_header_style), Paragraph("Avg Rating", table_header_style), Paragraph("Key Signal", table_header_style)],
        [Paragraph("Search Failures & Irrelevant Recs", table_body_bold), Paragraph("142", table_body_style), Paragraph("1.4★", table_body_style), Paragraph("Search typos fail; out-of-stock items boosted over available products.", table_body_style)],
        [Paragraph("Missing Product Specs & Expiry Dates", table_body_bold), Paragraph("118", table_body_style), Paragraph("1.6★", table_body_style), Paragraph("Users hesitate to buy fresh/gourmet without visible expiry dates.", table_body_style)],
        [Paragraph("Out-of-Stock Disruption", table_body_bold), Paragraph("105", table_body_style), Paragraph("1.8★", table_body_style), Paragraph("Frequent stockouts break habit loops and stop basket expansion.", table_body_style)],
        [Paragraph("Strict Refund & OTP Policy Friction", table_body_bold), Paragraph("85", table_body_style), Paragraph("1.2★", table_body_style), Paragraph("Complex OTP/return flows on fresh items create high trial fear.", table_body_style)]
    ]
    theme_table = Table(theme_table_data, colWidths=[160, 55, 65, 260])
    theme_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), SECONDARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ACCENT_BG])
    ]))
    story.append(theme_table)

    # SECTION 9
    story.append(Paragraph("9 · Honest Limitations", h1_style))
    lim_bullets = [
        "<b>Inferred segments</b>: user groups are estimated from review wording heuristics, not verified demographic data (app stores expose none).",
        "<b>Sample-based themes</b>: offline themes derive from a 450-review stratified sample; fixed seed (42) ensures exact reproducibility.",
        "<b>Ephemeral vector store</b>: on Streamlit Cloud, disk is ephemeral, so the vector index auto-rebuilds on cold start."
    ]
    for lb in lim_bullets:
        story.append(Paragraph(f"• {lb}", body_style))

    # SECTION 10
    story.append(Paragraph("10 · Tech Stack Summary", h1_style))
    stack_table_data = [
        [Paragraph("Layer", table_header_style), Paragraph("Technology Choice", table_header_style)],
        [Paragraph("Ingestion", table_body_bold), Paragraph("google-play-scraper, app-store-scraper, PRAW, YouTube API", table_body_style)],
        [Paragraph("Embeddings", table_body_bold), Paragraph("sentence-transformers all-MiniLM-L6-v2 (local, 384-dim)", table_body_style)],
        [Paragraph("Vector Store", table_body_bold), Paragraph("Chroma DB (file-persisted, keyed by review_id)", table_body_style)],
        [Paragraph("Generation", table_body_bold), Paragraph("Groq llama-3.3-70b-versatile (temperature=0.1)", table_body_style)],
        [Paragraph("Dashboard", table_body_bold), Paragraph("Streamlit (5 vertical navigation screens)", table_body_style)],
        [Paragraph("Live URL", table_body_bold), Paragraph("https://myntra-review-discovery-engine-b5yqfnvwidxrqxxmffftsf.streamlit.app/", table_body_style)]
    ]
    stack_table = Table(stack_table_data, colWidths=[120, page_width - 120])
    stack_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ACCENT_BG])
    ]))
    story.append(stack_table)

    # Build Document
    doc.build(story)
    print(f"PDF successfully built: {pdf_filename}")

if __name__ == "__main__":
    build_pdf()
