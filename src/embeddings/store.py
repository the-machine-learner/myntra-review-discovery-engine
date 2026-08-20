"""Chroma vector store for Myntra reviews and comments."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.errors import ChromaError

from src.config import PROCESSED_DIR, VECTOR_STORE_DIR
from src.ingestion.schema import NormalizedReview
from src.analysis.taxonomy import TAXONOMY

logger = logging.getLogger(__name__)

COLLECTION_NAME = "myntra_reviews"
CHECKPOINT_PATH = PROCESSED_DIR / "embed_checkpoint.json"


def compose_document(review: NormalizedReview | dict[str, Any], tags: list[str] | None = None) -> str:
    if isinstance(review, NormalizedReview):
        title, body = review.title, review.body
    else:
        title = str(review.get("title") or "")
        body = str(review.get("body") or "")
    text = f"{title} {body}".strip()

    # Doc2Query-style anchor-question injection, driven by the taxonomy's own
    # rule-based tags (computed once by the caller — see embeddings/run.py —
    # and passed in here, never re-derived) so retrieval recall improves for
    # question-style live queries. Unlike the old version this replaced, a
    # misconfigured taxonomy fails loudly here, not via a swallowed except.
    if tags:
        anchors: list[str] = []
        for area_id in tags:
            area = TAXONOMY.get(area_id)
            if area:
                anchors.extend(area.anchor_questions[:2])
        if anchors:
            unique_anchors = list(dict.fromkeys(anchors))
            text = f"{text}\n[Related questions: {' '.join(unique_anchors)}]"

    return text or body


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def review_metadata(
    review: NormalizedReview, doc_hash: str, tags: list[str] | None = None
) -> dict[str, str | int | bool]:
    meta: dict[str, str | int | bool] = {
        "review_id": review.review_id,
        "platform": review.platform,
        "rating": int(review.rating),
        "date": review.date,
        "app_version": review.app_version or "",
        "content_hash": doc_hash,
    }
    tag_set = set(tags or [])
    for area_id in TAXONOMY:
        meta[f"tag_{area_id}"] = area_id in tag_set
    meta["tag_count"] = len(tag_set)
    return meta


class ReviewVectorStore:
    def __init__(self, persist_dir: Path | None = None) -> None:
        path = str(persist_dir or VECTOR_STORE_DIR)
        self.persist_dir = Path(path)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        from chromadb.config import Settings
        self.client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection: Collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return self.collection.count()

    def stored_hashes(self) -> dict[str, str]:
        """review_id -> content_hash for all vectors in the collection."""
        total = self.count()
        if total == 0:
            return {}
        mapping: dict[str, str] = {}
        offset = 0
        page_size = 5000
        while offset < total:
            result = self.collection.get(
                include=["metadatas"],
                limit=page_size,
                offset=offset,
            )
            if not result["ids"]:
                break
            for review_id, meta in zip(result["ids"], result["metadatas"]):
                if meta and meta.get("content_hash"):
                    mapping[review_id] = str(meta["content_hash"])
            offset += len(result["ids"])
        return mapping

    def get_stored_hash(self, review_id: str) -> str | None:
        try:
            result = self.collection.get(ids=[review_id], include=["metadatas"])
        except Exception:
            return None
        if not result["ids"]:
            return None
        meta = result["metadatas"][0] or {}
        return str(meta.get("content_hash") or "") or None

    def needs_embedding(self, review_id: str, doc_hash: str) -> bool:
        stored = self.get_stored_hash(review_id)
        return stored != doc_hash

    def upsert_batch(
        self,
        reviews: list[NormalizedReview],
        embeddings: list[list[float]],
        documents: list[str],
        hashes: list[str],
        tags: list[list[str]] | None = None,
    ) -> None:
        if not reviews:
            return
        if not (len(reviews) == len(embeddings) == len(documents) == len(hashes)):
            raise ValueError("upsert_batch: mismatched list lengths")
        if tags is not None and len(tags) != len(reviews):
            raise ValueError("upsert_batch: tags length mismatch")

        ids = [r.review_id for r in reviews]
        tags = tags or [[] for _ in reviews]
        metadatas = [
            review_metadata(r, h, t) for r, h, t in zip(reviews, hashes, tags)
        ]
        
        # Split into small chunks to avoid Chroma payload limits
        chunk = 32
        for start in range(0, len(ids), chunk):
            end = start + chunk
            self._upsert_chunk(
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )

    def _upsert_chunk(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, str | int]],
        retries: int = 3,
    ) -> None:
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                self.collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                )
                return
            except ChromaError as exc:
                last_exc = exc
                logger.warning(
                    "Chroma upsert failed (attempt %s/%s, %s ids): %s",
                    attempt + 1,
                    retries,
                    len(ids),
                    exc,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Upsert failed (attempt %s/%s, %s ids): %s",
                    attempt + 1,
                    retries,
                    len(ids),
                    exc,
                )
        if last_exc is not None:
            raise last_exc

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        include_embeddings: bool = False,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        include = ["documents", "metadatas", "distances"]
        if include_embeddings:
            include.append("embeddings")
        kwargs: dict[str, Any] = dict(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=include,
        )
        if where:
            kwargs["where"] = where
        return self.collection.query(**kwargs)

    @staticmethod
    def distance_to_similarity(distance: float) -> float:
        """Chroma cosine distance -> similarity in [0, 1] (higher is more similar)."""
        return max(0.0, min(1.0, 1.0 - distance))

    def save_checkpoint(self, stats: dict[str, Any]) -> None:
        CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHECKPOINT_PATH.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    def load_checkpoint(self) -> dict[str, Any]:
        if not CHECKPOINT_PATH.exists():
            return {}
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
