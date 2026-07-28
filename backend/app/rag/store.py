"""Vector store.

Embeddings are computed by us and passed to Chroma explicitly, rather than
registering a Chroma ``EmbeddingFunction``. Chroma's embedding-function protocol
has changed shape across major versions; the ``add(embeddings=…)`` /
``query(query_embeddings=…)`` surface has not. Owning the embedding step keeps
this file stable across upgrades and keeps the model swappable in one place.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.core.logging import get_logger
from app.rag.chunking import Chunk
from app.rag.embeddings import get_embedder

logger = get_logger(__name__)


class VectorStore:
    """Persistent Chroma collection of doctrine chunks."""

    def __init__(self, collection_name: str | None = None) -> None:
        self.collection_name = collection_name or settings.vector_collection
        self._client = None
        self._collection = None

    def _ensure_collection(self):
        if self._collection is not None:
            return self._collection

        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            settings.vector_store_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(settings.vector_store_dir),
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:  # noqa: BLE001
            raise RetrievalError(f"Vector store unavailable: {exc}") from exc

        return self._collection

    # -- Write path ----------------------------------------------------------

    def index(self, chunks: list[Chunk], *, batch_size: int = 64) -> int:
        """Embed and upsert chunks. Idempotent — re-ingesting is safe."""
        if not chunks:
            return 0

        collection = self._ensure_collection()
        embedder = get_embedder()
        written = 0

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embedder.embed_documents([c.text for c in batch])
            collection.upsert(
                ids=[c.chunk_id for c in batch],
                documents=[c.text for c in batch],
                embeddings=vectors,
                metadatas=[c.metadata() for c in batch],
            )
            written += len(batch)
            logger.debug("rag.indexed_batch", written=written, total=len(chunks))

        logger.info("rag.indexed", chunks=written, collection=self.collection_name)
        return written

    def reset(self) -> None:
        collection = self._ensure_collection()
        existing = collection.get(include=[])
        ids = existing.get("ids", [])
        if ids:
            collection.delete(ids=ids)
            logger.info("rag.collection_cleared", removed=len(ids))

    # -- Read path -----------------------------------------------------------

    def query(
        self,
        text: str,
        *,
        top_k: int | None = None,
        hazard_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Similarity search returning documents with metadata and distance."""
        collection = self._ensure_collection()
        k = top_k or settings.rag_top_k

        where: dict[str, Any] | None = None
        if hazard_filter:
            # Match hazard-specific documents plus universally applicable ones.
            where = {"hazard": {"$in": [hazard_filter, "all", "multi"]}}

        vector = get_embedder().embed_query(text)
        raw = collection.query(
            query_embeddings=[vector],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        ids = (raw.get("ids") or [[]])[0]

        results: list[dict[str, Any]] = []
        for idx, document in enumerate(documents):
            distance = distances[idx] if idx < len(distances) else 1.0
            results.append(
                {
                    "chunk_id": ids[idx] if idx < len(ids) else f"chunk-{idx}",
                    "text": document,
                    "metadata": metadatas[idx] if idx < len(metadatas) else {},
                    # Cosine distance -> similarity in [0, 1].
                    "relevance": max(0.0, min(1.0, 1.0 - float(distance))),
                }
            )
        return results

    def count(self) -> int:
        try:
            return self._ensure_collection().count()
        except RetrievalError:
            return 0

    @property
    def is_populated(self) -> bool:
        return self.count() > 0


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
