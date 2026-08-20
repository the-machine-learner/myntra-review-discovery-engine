"""Shared Groq budget tracker.

Imported by both src/analysis/groq_client.py (batch analysis) and
src/rag/generator.py (live chat) so they draw from one coordinated budget
instead of two independent counters against the same Groq account/key.

Caveat (documented, not silently overclaimed): this only coordinates
batch-vs-live if both processes read/write the same persisted state file in
real time — true if both run on the same machine/container, not guaranteed if
batch runs in CI and live runs on a separately-hosted app. The real backstop
in that split-host case is Groq's own 429/Retry-After handling in
groq_client.py and rag/generator.py, which applies regardless.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from src.config import (
    PROCESSED_DIR,
    GROQ_RPM_LIMIT,
    GROQ_TPM_LIMIT,
    GROQ_RPD_LIMIT,
    GROQ_TPD_LIMIT,
    GROQ_LIVE_CHAT_RESERVED_PCT,
    GROQ_BUDGET_STATE_FILE,
)

STATE_PATH = PROCESSED_DIR / GROQ_BUDGET_STATE_FILE

Caller = Literal["batch", "live"]


@dataclass(frozen=True)
class BudgetDecision:
    ok: bool
    reason: str = ""


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _empty_state() -> dict:
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "date_utc": _today_utc(),
        "daily": {"calls_used": 0, "tokens_used": 0},
        "minute_window": [],
    }


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return _empty_state()
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    if state.get("date_utc") != _today_utc():
        return _empty_state()
    return state


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp_path.replace(STATE_PATH)  # atomic rename


def _prune_minute_window(state: dict) -> None:
    cutoff = time.time() - 60.0
    state["minute_window"] = [e for e in state["minute_window"] if e["ts"] >= cutoff]


def check_budget(estimated_tokens: int, caller: Caller) -> BudgetDecision:
    """Check whether a call of ~estimated_tokens is safe to make right now.

    `batch` respects a (1 - GROQ_LIVE_CHAT_RESERVED_PCT) ceiling on the daily
    budget so live chat always has reserved headroom; `live` can use the full
    daily ceiling.
    """
    state = _load_state()
    _prune_minute_window(state)

    minute_calls = len(state["minute_window"])
    minute_tokens = sum(e["tokens"] for e in state["minute_window"])

    if minute_calls + 1 > GROQ_RPM_LIMIT:
        return BudgetDecision(ok=False, reason="rpm_limit_reached")
    if minute_tokens + estimated_tokens > GROQ_TPM_LIMIT:
        return BudgetDecision(ok=False, reason="tpm_limit_reached")

    daily_calls = state["daily"]["calls_used"]
    daily_tokens = state["daily"]["tokens_used"]

    if caller == "batch":
        call_ceiling = int(GROQ_RPD_LIMIT * (1 - GROQ_LIVE_CHAT_RESERVED_PCT))
        token_ceiling = int(GROQ_TPD_LIMIT * (1 - GROQ_LIVE_CHAT_RESERVED_PCT))
    else:
        call_ceiling = GROQ_RPD_LIMIT
        token_ceiling = GROQ_TPD_LIMIT

    if daily_calls + 1 > call_ceiling:
        return BudgetDecision(ok=False, reason="daily_call_ceiling_reached")
    if daily_tokens + estimated_tokens > token_ceiling:
        return BudgetDecision(ok=False, reason="daily_token_ceiling_reached")

    return BudgetDecision(ok=True)


def record_usage(tokens_used: int, calls: int = 1) -> None:
    state = _load_state()
    _prune_minute_window(state)
    now = time.time()
    for _ in range(calls):
        state["minute_window"].append({"ts": now, "tokens": tokens_used})
    state["daily"]["calls_used"] += calls
    state["daily"]["tokens_used"] += tokens_used
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)


def remaining_capacity() -> dict:
    """For UI display — calls/tokens remaining this minute and today."""
    state = _load_state()
    _prune_minute_window(state)
    minute_calls = len(state["minute_window"])
    minute_tokens = sum(e["tokens"] for e in state["minute_window"])
    return {
        "date_utc": state["date_utc"],
        "minute_calls_remaining": max(0, GROQ_RPM_LIMIT - minute_calls),
        "minute_tokens_remaining": max(0, GROQ_TPM_LIMIT - minute_tokens),
        "daily_calls_remaining": max(0, GROQ_RPD_LIMIT - state["daily"]["calls_used"]),
        "daily_tokens_remaining": max(0, GROQ_TPD_LIMIT - state["daily"]["tokens_used"]),
    }
