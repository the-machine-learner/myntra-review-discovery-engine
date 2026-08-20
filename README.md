# ⚡ Myntra VOC Analysis Engine

A Voice-of-Customer (VOC) data pipeline that ingests customer reviews across 4 channels
(**Google Play Store, Apple App Store, YouTube Comments, X/Twitter**), normalizes them
into one corpus, and indexes them into a vector store for retrieval.

> Reddit was evaluated as a 5th channel (PRAW, then two Apify actors as
> no-login fallbacks) and removed — see git history (commit tagged "Reddit
> ingestion: Apify integration") for the full exploration if revisiting this.

> **Status:** the analysis layer (theme extraction, segmentation, user-needs, multi-category
> pipelines) and the output layer (Streamlit dashboard + RAG chatbot) were forked from the
> [Zepto VOC engine](../../Zepto/zepto-review-discovery-engine) and are being redesigned for
> Myntra's domain. The analysis layer has been removed; the old dashboard/chatbot app is parked
> under `reference/app/` for reference while both are rebuilt. Active today: **ingest → normalize
> → embed & index**.

---

## 📂 Project Structure

```
myntra-review-discovery-engine/
├── data/
│   ├── raw/                      # Raw ingested reviews from Play Store, App Store, YouTube, X
│   └── processed/                # normalized_reviews.json + embed_checkpoint.json
├── vector_store/                 # Chroma vector database persistent store
├── src/
│   ├── ingestion/                # Fetch, normalize, incremental-merge reviews per channel
│   ├── embeddings/                # Local/Groq embedder + Chroma vector store wrapper
│   ├── rag/
│   │   └── retriever.py          # ReviewRetriever — kept active, used by scripts/smoke_test.py
│   └── ops/
│       └── run.py                # Orchestrator: `python -m src.ops.run refresh` (ingest -> embed)
├── reference/
│   └── app/                      # Parked: old Streamlit dashboard (5 screens) + RAG chatbot logic
│       ├── streamlit_app.py      #   forked from the Zepto engine, not runnable as-is (no analysis
│       └── src/{dashboard,rag}/  #   artifacts) — kept for reference while the app is redesigned
├── .env.example                  # Environment configuration template
├── .gitignore
├── requirements.txt
└── generate_pdf.py
```

---

## 🛠️ Local Setup & Installation

### 1. Prerequisites
- Python 3.9+ installed on your system.

### 2. Clone & Install Dependencies
```bash
git clone <your-repository-url>
cd myntra-review-discovery-engine

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(Optional)* Add your `GROQ_API_KEY` to `.env` — unused until the RAG chatbot in `reference/app/` is rebuilt and reactivated.

---

## 🔄 Running the Pipeline

Ingest new reviews and refresh the vector index:

```bash
python -m src.ops.run refresh --incremental
```

Verify the index matches the corpus:

```bash
python scripts/verify_index.py
python scripts/smoke_test.py
```

---

## 🗂️ `reference/app/`

The Streamlit dashboard (5 screens) and RAG chatbot logic (`generator.py`, `pipeline.py`,
`fallback_answer.py`, `gate.py`) live here, forked as-is from the Zepto engine. They are **not
wired up** — `data_loader.py` expects analysis JSON artifacts (`themes.json`, `segments.json`,
etc.) that no longer exist, and the chatbot/dashboard imports won't resolve from this location.
Treat this folder as source material for the redesign, not a runnable app.
