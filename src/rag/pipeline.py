"""End-to-end RAG pipeline for chatbot queries. Ported from
reference/app/src/rag/pipeline.py — decision tree unchanged (empty-check ->
out-of-scope regex -> retrieve -> similarity-threshold gate -> shared-budget
gate -> Groq-enabled check -> generate -> citation-validate ->
fallback-on-any-failure), with one addition: a shared Groq budget check
(src/analysis/budget.py) before the Groq-enabled check, so live chat never
blocks a user — it routes straight to the zero-cost retrieval-only fallback
the moment the shared batch+live budget is tight.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.config import RAG_MAX_ANSWER_TOKENS, get_secret

from src.analysis.validators import validate_chat_answer
from src.analysis import budget
from src.rag.fallback_answer import build_retrieval_answer
from src.rag.gate import (
    OUT_OF_SCOPE_MESSAGE,
    REFUSAL_MESSAGE,
    is_out_of_scope,
    max_similarity,
    passes_threshold,
)
from src.rag.generator import generate_answer
from src.rag.retriever import RetrievedReview, ReviewRetriever

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    question: str
    answer: str
    retrieved: list[RetrievedReview] = field(default_factory=list)
    refused: bool = False
    groq_called: bool = False
    validation_ok: bool = True
    validation_errors: list[str] = field(default_factory=list)
    max_similarity: float = 0.0
    meta: dict = field(default_factory=dict)


def _fallback_enabled() -> bool:
    return str(get_secret("RAG_FALLBACK", "true")).lower() in ("1", "true", "yes")


def _use_groq() -> bool:
    return str(get_secret("RAG_USE_GROQ", "true")).lower() in ("1", "true", "yes")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _finish_with_fallback(
    question: str,
    retrieved: list[RetrievedReview],
    sim: float,
    reason: str,
) -> ChatResult:
    logger.info(f"[RAG Pipeline] Finishing with fallback answer. Reason: {reason}")
    answer = build_retrieval_answer(question, retrieved)
    return ChatResult(
        question=question,
        answer=answer,
        retrieved=retrieved,
        refused=False,
        groq_called=False,
        max_similarity=sim,
        meta={"fallback_reason": reason},
    )


def answer_question(
    question: str,
    retriever: ReviewRetriever,
    threshold: float | None = None,
    where: dict | None = None,
) -> ChatResult:
    """Run full RAG pipeline: gate -> retrieve -> budget-gate -> generate -> validate."""
    logger.info(f"[RAG Pipeline] Processing question: '{question}'")
    question = question.strip()
    if not question:
        return ChatResult(
            question=question,
            answer="Please enter a question about Myntra wishlist behavior or purchase decisions.",
            refused=True,
        )

    if is_out_of_scope(question):
        logger.warning("[RAG Pipeline] Out of scope question detected.")
        retrieved = retriever.retrieve(question, top_k=3, where=where)
        return ChatResult(
            question=question,
            answer=OUT_OF_SCOPE_MESSAGE,
            retrieved=retrieved,
            refused=True,
            groq_called=False,
            max_similarity=max_similarity(retrieved),
        )

    retrieved = retriever.retrieve(question, where=where)
    sim = max_similarity(retrieved)
    logger.info(f"[RAG Pipeline] Retrieved {len(retrieved)} reviews. Max similarity: {sim:.4f}")

    if not passes_threshold(retrieved, threshold):
        logger.warning(f"[RAG Pipeline] Max similarity {sim:.4f} is below threshold.")
        if _fallback_enabled() and retrieved:
            return _finish_with_fallback(question, retrieved, sim, "below_similarity_threshold")
        return ChatResult(
            question=question,
            answer=REFUSAL_MESSAGE,
            retrieved=retrieved,
            refused=True,
            groq_called=False,
            max_similarity=sim,
        )

    has_key = bool(get_secret("GROQ_API_KEY"))
    use_groq = _use_groq()
    logger.info(f"[RAG Pipeline] RAG_USE_GROQ={use_groq}, GROQ_API_KEY_PRESENT={has_key}")

    if not use_groq or not has_key:
        return _finish_with_fallback(question, retrieved, sim, "groq_disabled_or_missing_key")

    # Shared batch+live budget gate — a live user never blocks on a background
    # analysis job's spend; it just falls back to the zero-cost retrieval path.
    max_tokens = int(get_secret("RAG_MAX_ANSWER_TOKENS", str(RAG_MAX_ANSWER_TOKENS)))
    estimated = _estimate_tokens(question) + _estimate_tokens(str(retrieved)) + max_tokens
    decision = budget.check_budget(estimated, caller="live")
    if not decision.ok:
        logger.warning(f"[RAG Pipeline] Shared Groq budget exhausted: {decision.reason}")
        if _fallback_enabled():
            return _finish_with_fallback(question, retrieved, sim, "shared_budget_exhausted")
        return ChatResult(
            question=question,
            answer=REFUSAL_MESSAGE,
            retrieved=retrieved,
            refused=True,
            groq_called=False,
            max_similarity=sim,
            meta={"reason": decision.reason},
        )

    allowed_ids = {r.review_id for r in retrieved}
    try:
        logger.info("[RAG Pipeline] Calling Groq API for LLM answer generation...")
        answer, meta = generate_answer(question, retrieved)
        logger.info("[RAG Pipeline] Groq LLM response received successfully.")
    except Exception as exc:
        reason = type(exc).__name__
        logger.error(f"[RAG Pipeline] Groq API call failed: {exc}", exc_info=True)
        if _fallback_enabled():
            return _finish_with_fallback(question, retrieved, sim, f"groq_error_{reason}")
        return ChatResult(
            question=question,
            answer=f"Error generating answer: {exc}. Showing retrieved reviews instead.",
            retrieved=retrieved,
            refused=True,
            groq_called=False,
            max_similarity=sim,
        )

    validation = validate_chat_answer(answer, allowed_ids)
    if not validation.ok:
        logger.warning(f"[RAG Pipeline] Answer validation failed: {validation.errors}")
        if _fallback_enabled():
            return _finish_with_fallback(question, retrieved, sim, "validation_failed")
        return ChatResult(
            question=question,
            answer="Answer failed validation. See source excerpts below.",
            retrieved=retrieved,
            refused=True,
            groq_called=True,
            validation_ok=False,
            validation_errors=validation.errors,
            max_similarity=sim,
            meta=meta,
        )

    logger.info("[RAG Pipeline] RAG query completed cleanly with LLM response.")
    return ChatResult(
        question=question,
        answer=answer,
        retrieved=retrieved,
        refused=False,
        groq_called=True,
        validation_ok=True,
        max_similarity=sim,
        meta=meta,
    )
