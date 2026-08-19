"""Validate LLM analysis artifacts for Myntra VOC Engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.ingestion.schema import NormalizedReview

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
)

# Broadened to match our custom review_ids (e.g. gp_rev_0, as_rev_1, reddit_post_1s5dwjy, etc.)
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


def validate_themes(
    themes: list[dict],
    corpus: dict[str, NormalizedReview],
    max_themes: int = 5,
    max_summary_words: int = 250,
) -> ValidationResult:
    errors: list[str] = []
    if not themes:
        errors.append("No themes produced")
        return ValidationResult(ok=False, errors=["No themes produced"])
        
    if len(themes) > max_themes:
        errors.append(f"Theme count {len(themes)} exceeds max {max_themes}")

    for i, theme in enumerate(themes):
        label = theme.get("label", f"theme_{i}")
        summary = theme.get("summary", "")
        if word_count(summary) > max_summary_words:
            errors.append(f"{label}: summary exceeds {max_summary_words} words")

        quotes = theme.get("quotes", [])
        if len(quotes) < 1:
            errors.append(f"{label}: needs at least 1 quote")

        for quote in quotes:
            text = quote.get("text", "")
            rid = quote.get("review_id", "")
            if has_pii(text):
                errors.append(f"{label}: quote contains PII")
            if rid not in corpus:
                errors.append(f"{label}: unknown review_id {rid}")
            elif not quote_in_corpus(text, corpus[rid].body):
                errors.append(f"{label}: quote not found in review {rid}")

        for rid in theme.get("supporting_review_ids", []):
            if rid not in corpus:
                errors.append(f"{label}: supporting review_id {rid} not in corpus")

    return ValidationResult(ok=not errors, errors=errors)


def validate_unmet_needs(
    needs: list[dict],
    corpus: dict[str, NormalizedReview],
    max_needs: int = 5,
) -> ValidationResult:
    errors: list[str] = []
    if len(needs) > max_needs:
        errors.append(f"Unmet needs count {len(needs)} exceeds {max_needs}")
    for need in needs:
        if has_pii(need.get("statement", "")):
            errors.append("Unmet need statement contains PII")
        for rid in need.get("supporting_review_ids", []):
            if rid not in corpus:
                errors.append(f"Unmet need cites unknown review_id {rid}")
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
