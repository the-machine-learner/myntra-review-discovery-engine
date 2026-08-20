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

# Reddit configurations
REDDIT_CLIENT_ID = get_secret("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = get_secret("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = get_secret("REDDIT_USER_AGENT", "macos:com.discoveryengine.scraper:v1.0.0 (by /u/prodkins)")

# Apify Reddit Scraper (fallback Reddit source when PRAW credentials are absent).
# spry_wholemeal/reddit-scraper: pay-per-Apify-usage, no monthly rental fee —
# chosen over harshmaur/reddit-scraper-pro ($20/mo rental) since it fits a
# Free-tier Apify account's $5/mo included usage with no risk of surprise billing.
APIFY_API_TOKEN = get_secret("APIFY_API_TOKEN", "")
APIFY_REDDIT_ACTOR_ID = get_secret("APIFY_REDDIT_ACTOR_ID", "spry_wholemeal/reddit-scraper")
APIFY_MAX_POSTS_PER_QUERY = int(get_secret("APIFY_MAX_POSTS_PER_QUERY", "40"))
APIFY_MAX_COMMENTS_PER_POST = int(get_secret("APIFY_MAX_COMMENTS_PER_POST", "10"))

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


