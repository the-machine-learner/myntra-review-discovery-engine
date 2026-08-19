"""Retrieve reviews from Chroma using the embedding model and MMR re-ranking."""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.config import RAG_FETCH_K, RAG_MMR_LAMBDA, RAG_TOP_K, LOCAL_EMBEDDING_MODEL, get_secret
from src.embeddings.local_embedder import LocalEmbedder
from src.embeddings.store import ReviewVectorStore


@dataclass(frozen=True)
class RetrievedReview:
    review_id: str
    document: str
    rating: int
    date: str
    platform: str
    app_version: str
    similarity: float


class ReviewRetriever:
    """Wraps vector database retrieval with MMR re-ranking."""

    def __init__(self) -> None:
        self.store = ReviewVectorStore()
        model = get_secret("LOCAL_EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL)
        self.embedder = LocalEmbedder(model_name=model)

    @property
    def corpus_size(self) -> int:
        return self.store.count()

    def retrieve(self, question: str, top_k: int | None = None) -> list[RetrievedReview]:
        k = top_k if top_k is not None else int(get_secret("RAG_TOP_K", str(RAG_TOP_K)))
        count = self.store.count()
        if count == 0:
            return []

        fetch_k = max(k, int(get_secret("RAG_FETCH_K", str(RAG_FETCH_K))))
        vector = self.embedder.embed_one(question)
        results = self.store.query(
            vector,
            n_results=min(fetch_k, count),
            include_embeddings=True,
        )

        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]
        embeddings = (results.get("embeddings") or [None])[0]

        candidates: list[RetrievedReview] = []
        for rid, doc, meta, dist in zip(ids, documents, metadatas, distances):
            meta = meta or {}
            candidates.append(
                RetrievedReview(
                    review_id=str(rid),
                    document=str(doc or ""),
                    rating=int(meta.get("rating", 0)),
                    date=str(meta.get("date", "")),
                    platform=str(meta.get("platform", "google_play")),
                    app_version=str(meta.get("app_version", "")),
                    similarity=ReviewVectorStore.distance_to_similarity(float(dist)),
                )
            )

        order = self._mmr_order(vector, embeddings, len(candidates), k)
        return [candidates[i] for i in order]

    @staticmethod
    def _mmr_order(
        query_vec: list[float],
        cand_vecs: list[list[float]] | None,
        n_candidates: int,
        k: int,
    ) -> list[int]:
        """Return candidate indices reordered by MMR. Falls back to Chroma's
        relevance order if embeddings are unavailable or anything goes wrong."""
        fallback = list(range(min(k, n_candidates)))
        if cand_vecs is None or n_candidates == 0:
            return fallback
        try:
            import numpy as np
            np.seterr(all='ignore')

            lambda_mult = float(get_secret("RAG_MMR_LAMBDA", str(RAG_MMR_LAMBDA)))
            q = np.asarray(query_vec, dtype=float)
            mat = np.asarray(cand_vecs, dtype=float)
            if mat.ndim != 2 or mat.shape[0] != n_candidates:
                return fallback

            q_norm = q / (np.linalg.norm(q) + 1e-9)
            mat_norm = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
            query_sim = mat_norm @ q_norm
            sim_matrix = mat_norm @ mat_norm.T

            selected: list[int] = []
            remaining = set(range(n_candidates))
            target = min(k, n_candidates)
            while remaining and len(selected) < target:
                if not selected:
                    best = max(remaining, key=lambda i: query_sim[i])
                else:
                    best = max(
                        remaining,
                        key=lambda i: lambda_mult * query_sim[i]
                        - (1.0 - lambda_mult) * max(sim_matrix[i][j] for j in selected),
                    )
                selected.append(best)
                remaining.discard(best)
            return selected
        except Exception:
            return fallback
