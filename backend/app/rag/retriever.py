"""Cited retrieval.

The retriever's contract is stricter than "return similar text": it returns
:class:`Citation` objects carrying the issuing authority, the section, and a
verbatim snippet. Agents are then instructed to ground claims in those
citations. In emergency doctrine an uncited recommendation is not actionable —
a commander must be able to check what the guidance actually says.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.core.logging import get_logger
from app.rag.store import get_vector_store
from app.schemas.common import Citation

logger = get_logger(__name__)

#: Below this cosine similarity a chunk is noise. Returning weak matches is
#: worse than returning nothing: it invites the model to ground an answer in
#: irrelevant doctrine and cite it authoritatively.
MIN_RELEVANCE = 0.28


@dataclass
class RetrievedChunk:
    text: str
    citation: Citation
    relevance: float


@dataclass
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    degraded: bool = False
    reason: str | None = None

    @property
    def citations(self) -> list[Citation]:
        return [c.citation for c in self.chunks]

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    def as_context(self, max_chars: int = 6000) -> str:
        """Format retrieved doctrine for injection into a prompt."""
        if self.is_empty:
            return (
                "NO DOCTRINE RETRIEVED. Do not invent guidance or cite sources. "
                "State explicitly that doctrinal grounding was unavailable."
            )

        blocks: list[str] = []
        used = 0
        for index, chunk in enumerate(self.chunks, start=1):
            block = (
                f"[{index}] {chunk.citation.document_title} "
                f"— §{chunk.citation.section} "
                f"({chunk.citation.authority}, id={chunk.citation.source_id}, "
                f"relevance={chunk.relevance:.2f})\n{chunk.text.strip()}"
            )
            if used + len(block) > max_chars:
                break
            blocks.append(block)
            used += len(block)

        return "\n\n---\n\n".join(blocks)


class DoctrineRetriever:
    """Query interface over the doctrine vector store."""

    def __init__(self) -> None:
        self._store = get_vector_store()

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        hazard: str | None = None,
        min_relevance: float = MIN_RELEVANCE,
    ) -> RetrievalResult:
        if not query.strip():
            return RetrievalResult(query=query, chunks=[], degraded=True, reason="empty query")

        try:
            raw = self._store.query(
                query, top_k=top_k or settings.rag_top_k, hazard_filter=hazard
            )
        except RetrievalError as exc:
            logger.warning("rag.retrieve_failed", error=str(exc)[:200])
            return RetrievalResult(query=query, chunks=[], degraded=True, reason=str(exc))

        chunks: list[RetrievedChunk] = []
        for row in raw:
            if row["relevance"] < min_relevance:
                continue
            meta: dict[str, Any] = row.get("metadata") or {}
            chunks.append(
                RetrievedChunk(
                    text=row["text"],
                    relevance=row["relevance"],
                    citation=Citation(
                        source_id=meta.get("document_id", row["chunk_id"]),
                        document_title=meta.get("document_title", "Unknown document"),
                        section=meta.get("section"),
                        snippet=_snippet(row["text"]),
                        relevance=row["relevance"],
                        authority=meta.get("authority"),
                    ),
                )
            )

        logger.debug(
            "rag.retrieved",
            query=query[:80],
            hazard=hazard,
            returned=len(chunks),
            considered=len(raw),
        )
        return RetrievalResult(query=query, chunks=chunks)

    def multi_query(
        self, queries: list[str], *, top_k: int = 3, hazard: str | None = None
    ) -> RetrievalResult:
        """Retrieve across several sub-questions and merge, de-duplicated.

        Prompt-chaining pattern: the Knowledge Agent decomposes one operational
        question into several targeted retrievals, which materially outperforms
        a single broad query on multi-part questions.
        """
        merged: dict[str, RetrievedChunk] = {}
        for query in queries:
            for chunk in self.retrieve(query, top_k=top_k, hazard=hazard).chunks:
                key = f"{chunk.citation.source_id}:{chunk.citation.section}"
                # Keep the strongest match for a given section.
                if key not in merged or chunk.relevance > merged[key].relevance:
                    merged[key] = chunk

        ordered = sorted(merged.values(), key=lambda c: c.relevance, reverse=True)
        return RetrievalResult(query=" | ".join(queries), chunks=ordered)


def _snippet(text: str, limit: int = 320) -> str:
    """Verbatim excerpt, trimmed to a sentence boundary where possible."""
    body = text.split("\n\n", 1)[-1].strip() if "\n\n" in text else text.strip()
    if len(body) <= limit:
        return body
    cut = body[:limit]
    last_stop = cut.rfind(". ")
    return (cut[: last_stop + 1] if last_stop > limit * 0.5 else cut).strip() + "…"


@lru_cache
def get_retriever() -> DoctrineRetriever:
    return DoctrineRetriever()
