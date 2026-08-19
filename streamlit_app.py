"""Root entry point for Streamlit."""

import sys
import streamlit as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(
    page_title="Myntra VOC Analysis Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.dashboard import app

if __name__ == "__main__":
    app.main()
