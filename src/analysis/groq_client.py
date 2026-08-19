"""Groq chat client for analysis stages."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import deque
from typing import Any

from src.config import GROQ_CALL_SLEEP_S, GROQ_CHAT_MODEL, get_secret

logger = logging.getLogger(__name__)

JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


def _throttle_enabled() -> bool:
    return get_secret("GROQ_THROTTLE", "false").lower() in ("1", "true", "yes")


class AnalysisGroqClient:
    def __init__(self, model: str | None = None, sleep_s: float | None = None) -> None:
        self.key = get_secret("GROQ_API_KEY")
        self._client = None
        self.model = model or get_secret("GROQ_CHAT_MODEL", GROQ_CHAT_MODEL)
        self.sleep_s = float(sleep_s if sleep_s is not None else get_secret("GROQ_CALL_SLEEP_S", str(GROQ_CALL_SLEEP_S)))
        self.tpm_limit = int(get_secret("GROQ_TPM_LIMIT", "120000"))
        self.rpm_limit = int(get_secret("GROQ_RPM_LIMIT", "1000"))
        self.call_count = 0
        self.estimated_tokens = 0
        self._recent_calls: deque[float] = deque()
        self._recent_tokens: deque[tuple[float, int]] = deque()

    @property
    def client(self):
        if self._client is None:
            if not self.key:
                raise RuntimeError("GROQ_API_KEY is not set in .env. Please add it to run LLM analysis.")
            from groq import Groq
            self._client = Groq(api_key=self.key, max_retries=10)
        return self._client

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _prune_window(self, now: float, window_s: float = 60.0) -> None:
        cutoff = now - window_s
        while self._recent_calls and self._recent_calls[0] < cutoff:
            self._recent_calls.popleft()
        while self._recent_tokens and self._recent_tokens[0][0] < cutoff:
            self._recent_tokens.popleft()

    def _tokens_in_window(self) -> int:
        return sum(tokens for _, tokens in self._recent_tokens)

    def _wait_for_quota(self, estimated_request_tokens: int) -> None:
        if not _throttle_enabled():
            return

        now = time.time()
        self._prune_window(now)

        if len(self._recent_calls) >= self.rpm_limit:
            wait = 60.0 - (now - self._recent_calls[0]) + 0.5
            if wait > 0:
                logger.info("RPM cap (%s/min); sleeping %.1fs", self.rpm_limit, wait)
                time.sleep(wait)
                now = time.time()
                self._prune_window(now)

        tokens_used = self._tokens_in_window()
        if tokens_used + estimated_request_tokens > self.tpm_limit and self._recent_tokens:
            wait = 60.0 - (now - self._recent_tokens[0][0]) + 1.0
            if wait > 0:
                logger.info("TPM cap; sleeping %.1fs", wait)
                time.sleep(wait)

        if self.call_count and self.sleep_s > 0:
            time.sleep(self.sleep_s)

    @staticmethod
    def _retry_after_seconds(exc: Any) -> float | None:
        response = getattr(exc, "response", None)
        if response is None:
            return None
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        raw = headers.get("retry-after")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def chat_json(self, system: str, user: str, max_retries: int = 8) -> Any:
        from groq import RateLimitError
        estimated = self._estimate_tokens(system + user) + 512

        for attempt in range(max_retries):
            try:
                self._wait_for_quota(estimated)

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                now = time.time()
                self.call_count += 1
                self._recent_calls.append(now)

                content = response.choices[0].message.content or "{}"
                usage = getattr(response, "usage", None)
                total_tokens = estimated
                if usage and getattr(usage, "total_tokens", None):
                    total_tokens = int(usage.total_tokens)
                self._recent_tokens.append((now, total_tokens))
                self.estimated_tokens += total_tokens

                return self._parse_json(content)
            except RateLimitError as exc:
                retry_after = self._retry_after_seconds(exc)
                wait = retry_after if retry_after is not None else max(5.0, self.sleep_s * (2 ** attempt))
                logger.warning("Rate limited (attempt %s/%s); sleeping %.1fs", attempt + 1, max_retries, wait)
                time.sleep(wait)
            except json.JSONDecodeError as exc:
                if attempt == max_retries - 1:
                    raise
                logger.warning("JSON parse failed, retrying: %s", exc)
        raise RuntimeError("Groq chat_json failed after retries")

    @staticmethod
    def _parse_json(content: str) -> Any:
        content = content.strip()
        block = JSON_BLOCK.search(content)
        if block:
            content = block.group(1).strip()
        return json.loads(content)
