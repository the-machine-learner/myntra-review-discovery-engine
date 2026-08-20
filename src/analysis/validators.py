"""Validate LLM analysis output for the Myntra VOC Engine — citation checks
(quotes must be real reviews from the retrieved/sampled set), PII scrubbing,
and length bounds. Revived from git history (commit 5808aa6), generalized
from the old theme/unmet-needs shapes to the new opportunity-synthesis shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.ingestion.schema import NormalizedReview

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
)

CITATION_PATTERN = re.compile(
    r"\[review_id:\s*([a-zA-Z0-9_:-]+)\]|review_id:\s*([a-zA-Z0-9_:-]+)",
    re.I,
)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


def word_count(text: str) -> int:
    return len(text.split())


def has_pii(text: str) -> bool:
    return bool(EMAIL_PATTERN.search(text) or PHONE_PATTERN.search(text))


def has_pii_excluding_citations(text: str) -> bool:
    cleaned = CITATION_PATTERN.sub("", text)
    return has_pii(cleaned)


def quote_in_corpus(quote: str, body: str) -> bool:
    q = re.sub(r"\s+", " ", quote.strip().lower())
    b = re.sub(r"\s+", " ", body.strip().lower())
    if not q:
        return False
    return q in b


def validate_opportunity_synthesis(
    area_id: str,
    llm_synthesis: str,
    top_quotes: list[dict],
    corpus: dict[str, NormalizedReview],
    max_synthesis_words: int = 200,
) -> ValidationResult:
    """Validate one opportunity area's LLM synthesis output: PII-free,
    within length bounds, and every quote traceable to a real review in the
    sampled corpus (never fabricated)."""
    errors: list[str] = []

    if not llm_synthesis.strip():
        errors.append(f"{area_id}: empty synthesis")
    elif word_count(llm_synthesis) > max_synthesis_words:
        errors.append(f"{area_id}: synthesis exceeds {max_synthesis_words} words")
    if has_pii(llm_synthesis):
        errors.append(f"{area_id}: synthesis contains PII")

    if not top_quotes:
        errors.append(f"{area_id}: needs at least 1 supporting quote")

    for quote in top_quotes:
        text = quote.get("text", "")
        rid = quote.get("review_id", "")
        if has_pii(text):
            errors.append(f"{area_id}: quote contains PII")
        if rid not in corpus:
            errors.append(f"{area_id}: unknown review_id {rid}")
        elif not quote_in_corpus(text, corpus[rid].body):
            errors.append(f"{area_id}: quote not found verbatim in review {rid}")

    return ValidationResult(ok=not errors, errors=errors)


def extract_cited_review_ids(text: str) -> list[str]:
    ids: list[str] = []
    for m in CITATION_PATTERN.finditer(text):
        rid = m.group(1) or m.group(2)
        if rid and rid not in ids:
            ids.append(rid)
    return ids


def validate_chat_answer(
    answer: str,
    allowed_review_ids: set[str],
    require_citation: bool = True,
) -> ValidationResult:
    errors: list[str] = []
    if not answer.strip():
        errors.append("Empty answer")
        return ValidationResult(ok=False, errors=errors)

    if has_pii_excluding_citations(answer):
        errors.append("Answer contains PII")

    cited = extract_cited_review_ids(answer)
    if require_citation and not cited:
        errors.append("Answer missing review_id citation")

    for rid in cited:
        if rid not in allowed_review_ids:
            errors.append(f"Citation references review_id not in retrieved set: {rid}")

    return ValidationResult(ok=not errors, errors=errors)
