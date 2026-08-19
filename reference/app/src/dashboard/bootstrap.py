"""Bootstrap path, .env, and optional Streamlit secrets for Myntra VOC Engine."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import PROJECT_ROOT  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")


def _flatten_secrets(secrets) -> dict[str, str]:
    """Flatten st.secrets into a flat {KEY: value} dict."""
    flat: dict[str, str] = {}
    try:
        items = list(secrets.items())
    except Exception:
        return flat
    for key, value in items:
        if isinstance(value, str):
            flat.setdefault(key, value)
        else:
            try:
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, str):
                        flat.setdefault(sub_key, sub_value)
            except Exception:
                continue
    return flat


def apply_streamlit_secrets(st_module) -> None:
    """Map Streamlit secrets into os.environ."""
    try:
        flat = _flatten_secrets(st_module.secrets)
    except Exception:
        return
    for key, value in flat.items():
        if not os.environ.get(key):
            os.environ[key] = value


def secret_key_names(st_module) -> list[str]:
    """Return visible secret key NAMES (never values) for safe diagnostics."""
    try:
        return sorted(_flatten_secrets(st_module.secrets).keys())
    except Exception:
        return []
