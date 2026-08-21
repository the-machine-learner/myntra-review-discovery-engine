from __future__ import annotations

import os
import logging
from sentence_transformers import SentenceTransformer

from src.config import LOCAL_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

class LocalEmbedder:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or LOCAL_EMBEDDING_MODEL
        logger.info("Loading local embedding model: %s", self.model_name)
        
        # Determine if we should attempt local files only
        local_only = os.getenv("HF_HUB_OFFLINE", "1").lower() in ("1", "true", "yes")
        try:
            self.model = SentenceTransformer(self.model_name, local_files_only=local_only, device="cpu")
        except Exception as e:
            logger.warning("Local-only load attempt failed/offline (%s). Attempting online download if available...", e)
            try:
                self.model = SentenceTransformer(self.model_name, local_files_only=False, device="cpu")
            except Exception as online_err:
                logger.error("Could not load sentence-transformers model online or offline: %s", online_err)
                raise online_err
                
        self.api_call_count = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(texts, show_progress_bar=False)
        self.api_call_count += 1
        return [v.tolist() for v in vectors]

    def embed_one(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]
