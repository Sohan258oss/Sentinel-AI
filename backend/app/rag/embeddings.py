"""Embedding provider.

fastembed (ONNX) rather than sentence-transformers: no torch dependency for the
RAG path, ~10x smaller install, and fast enough on CPU that retrieval never
becomes the bottleneck in a live demo. The vision subsystem owns torch; the
retrieval subsystem should not have to.

Model weights download once on first use and are cached locally thereafter.
"""

from __future__ import annotations

import threading
from functools import lru_cache

from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.core.logging import get_logger

logger = get_logger(__name__)


class Embedder:
    """Thread-safe lazy wrapper around a fastembed text model."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.embedding_model
        self._model = None
        self._lock = threading.Lock()
        self._dimension: int | None = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from fastembed import TextEmbedding

                logger.info("rag.embedder.loading", model=self.model_name)
                self._model = TextEmbedding(model_name=self.model_name)
                logger.info("rag.embedder.ready", model=self.model_name)
            except Exception as exc:  # noqa: BLE001 - surfaced as RetrievalError
                raise RetrievalError(
                    f"Could not load embedding model '{self.model_name}': {exc}"
                ) from exc
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_model()
        vectors = [list(map(float, v)) for v in model.embed(texts)]
        if vectors:
            self._dimension = len(vectors[0])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        model = self._ensure_model()
        # fastembed exposes a query-specific path for asymmetric models
        # (bge expects a query prefix); fall back to the document path if the
        # installed version does not provide it.
        embed_query = getattr(model, "query_embed", None)
        if callable(embed_query):
            vectors = [list(map(float, v)) for v in embed_query([text])]
            if vectors:
                return vectors[0]
        return self.embed_documents([text])[0]

    @property
    def dimension(self) -> int | None:
        return self._dimension

    def warm(self) -> bool:
        """Pre-load the model at startup so the first query is not slow."""
        try:
            self.embed_documents(["warmup"])
            return True
        except RetrievalError as exc:
            logger.warning("rag.embedder.warm_failed", error=str(exc)[:200])
            return False


@lru_cache
def get_embedder() -> Embedder:
    return Embedder()
