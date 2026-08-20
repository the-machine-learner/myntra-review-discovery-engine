"""Retrieval-only answers when Groq is unavailable, budget-exhausted, or
validation fails. Pure string templating, zero LLM cost — the "always
available" chat path. Ported near-verbatim from reference/app.
"""

from __future__ import annotations

from src.rag.retriever import RetrievedReview


def build_retrieval_answer(question: str, retrieved: list[RetrievedReview]) -> str:
    if not retrieved:
        return "No matching reviews were found in the corpus."

    intro = (
        f"Here is what **{len(retrieved)}** retrieved Myntra/Ajio customer reviews suggest "
        f"(similarity {retrieved[0].similarity:.2f}–{retrieved[-1].similarity:.2f}):\n\n"
    )
    bullets: list[str] = []
    for item in retrieved[:6]:
        text = item.document.strip()
        if len(text) > 220:
            text = text[:220].rsplit(" ", 1)[0] + "…"
        bullets.append(
            f"- ({item.rating}★, {item.date}, platform={item.platform}) {text} [review_id: {item.review_id}]"
        )

    return intro + "\n".join(bullets)
