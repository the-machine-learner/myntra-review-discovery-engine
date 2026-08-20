"""Root entry point for Streamlit.

Note: st.set_page_config() is called inside src/dashboard/app.py at import
time — it must not also be called here, since Streamlit only allows one call
per session and a second call raises.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard import app

if __name__ == "__main__":
    app.main()
