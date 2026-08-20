"""Project configuration defaults (supporting Streamlit st.secrets and local .env)."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file at the project root if it exists
PROJECT_ROOT = Path(__file__).resolve().parents[1]
dotenv_file = PROJECT_ROOT / ".env"
if dotenv_file.is_file():
    load_dotenv(dotenv_file)

def get_secret(key: str, default: str = "") -> str:
    """Retrieve secret/config value prioritizing Streamlit st.secrets over os.getenv."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            val = st.secrets[key]
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)

DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw"
VECTOR_STORE_DIR = PROJECT_ROOT / "vector_store"

# Ingestion settings
PACKAGE_NAME = get_secret("PACKAGE_NAME", "com.myntra.android")
APP_STORE_ID = int(get_secret("APP_STORE_ID", "907394059"))
LOOKBACK_WEEKS = int(get_secret("LOOKBACK_WEEKS", "10"))
MIN_WORD_COUNT = int(get_secret("MIN_WORD_COUNT", "6"))

# MouthShut ingestion (needs Playwright + Chromium — see requirements.txt).
# Sequential pagination (page 1,2,3,4,5,6...) reliably starts silently
# repeating already-seen content around page 6 (confirmed via diagnostic
# testing — still HTTP 200 with 20 reviews, just duplicates, no error).
# Fetching the same pages in SHUFFLED order reliably avoids this (see
# fetch_mouthshut() for the full finding) — pages are always requested
# out of order, never sequentially.
MOUTHSHUT_PRODUCT_SLUG = get_secret("MOUTHSHUT_PRODUCT_SLUG", "myntra-reviews-925076140")
MOUTHSHUT_MAX_PAGES = int(get_secret("MOUTHSHUT_MAX_PAGES", "50"))

# Embeddings configuration
EMBEDDING_BACKEND = get_secret("EMBEDDING_BACKEND", "local")
LOCAL_EMBEDDING_MODEL = get_secret("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
GROQ_EMBEDDING_MODEL = get_secret("GROQ_EMBEDDING_MODEL", "nomic-embed-text-v1.5")
EMBED_BATCH_SIZE = int(get_secret("EMBED_BATCH_SIZE", "128"))
EMBED_BATCH_SLEEP_S = float(get_secret("EMBED_BATCH_SLEEP_S", "1.0"))

# LLM Chat Model configuration
GROQ_CHAT_MODEL = get_secret("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")
ANALYSIS_SAMPLE_CAP = int(get_secret("ANALYSIS_SAMPLE_CAP", "450"))
UNMET_NEEDS_SAMPLE_CAP = int(get_secret("UNMET_NEEDS_SAMPLE_CAP", "300"))
ANALYSIS_BATCH_SIZE = int(get_secret("ANALYSIS_BATCH_SIZE", "20"))
GROQ_CALL_SLEEP_S = float(get_secret("GROQ_CALL_SLEEP_S", "0.5"))

# RAG chatbot
RAG_TOP_K = int(get_secret("RAG_TOP_K", "8"))
RAG_FETCH_K = int(get_secret("RAG_FETCH_K", "40"))
RAG_MMR_LAMBDA = float(get_secret("RAG_MMR_LAMBDA", "0.7"))
RAG_SIMILARITY_THRESHOLD = float(get_secret("RAG_SIMILARITY_THRESHOLD", "0.30"))
RAG_MAX_ANSWER_TOKENS = int(get_secret("RAG_MAX_ANSWER_TOKENS", "512"))
RAG_USE_GROQ = str(get_secret("RAG_USE_GROQ", "true")).lower() == "true"
RAG_FALLBACK = str(get_secret("RAG_FALLBACK", "true")).lower() == "true"
USE_GROQ_SEGMENTATION = str(get_secret("USE_GROQ_SEGMENTATION", "false")).lower() == "true"
SERPAPI_API_KEY = get_secret("SERPAPI_API_KEY", "")
GROQ_API_KEY = get_secret("GROQ_API_KEY", "")

# Groq free-tier throttle — realistic free-tier limits for llama-3.3-70b-versatile
GROQ_RPM_LIMIT = int(get_secret("GROQ_RPM_LIMIT", "28"))
GROQ_TPM_LIMIT = int(get_secret("GROQ_TPM_LIMIT", "11000"))
GROQ_THROTTLE = str(get_secret("GROQ_THROTTLE", "true")).lower() == "true"

# Shared batch+live daily budget (placeholders — confirm against your Groq console)
GROQ_RPD_LIMIT = int(get_secret("GROQ_RPD_LIMIT", "1000"))
GROQ_TPD_LIMIT = int(get_secret("GROQ_TPD_LIMIT", "500000"))
GROQ_LIVE_CHAT_RESERVED_PCT = float(get_secret("GROQ_LIVE_CHAT_RESERVED_PCT", "0.25"))
GROQ_BUDGET_STATE_FILE = get_secret("GROQ_BUDGET_STATE_FILE", "groq_budget_state.json")

# Opportunity-area analysis
ANALYSIS_PROMPT_VERSION = get_secret("ANALYSIS_PROMPT_VERSION", "wishlist_v1")
OPPORTUNITY_SAMPLE_CAP_PER_AREA = int(get_secret("OPPORTUNITY_SAMPLE_CAP_PER_AREA", "40"))


