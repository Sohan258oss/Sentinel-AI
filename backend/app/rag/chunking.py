"""Document parsing and chunking.

Chunking strategy is heading-aware rather than fixed-window. Doctrine documents
are organised into meaningful sections ("Allocation priority order", "Triage
categories"), and a chunk that spans a section boundary retrieves badly and
cites worse. Each chunk therefore carries its section title, which is what lets
a citation say *"DOC-ALLOC-04 §3 Sourcing rules"* instead of *"chunk 47"*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class Chunk:
    """One retrievable unit of doctrine."""

    chunk_id: str
    text: str
    document_id: str
    document_title: str
    authority: str
    section: str
    source_path: str
    hazard: str = "all"
    phase: str = "response"
    provenance: str = ""

    def metadata(self) -> dict[str, Any]:
        # Chroma metadata values must be scalars.
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "authority": self.authority,
            "section": self.section,
            "source_path": self.source_path,
            "hazard": self.hazard,
            "phase": self.phase,
            "provenance": self.provenance[:900],
        }


@dataclass
class ParsedDocument:
    path: Path
    frontmatter: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def document_id(self) -> str:
        return self.frontmatter.get("document_id", self.path.stem.upper())

    @property
    def title(self) -> str:
        return self.frontmatter.get("title", self.path.stem.replace("_", " ").title())

    @property
    def authority(self) -> str:
        return self.frontmatter.get("authority", "SentinelAI Doctrine Digest")


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Minimal YAML-frontmatter reader.

    Deliberately hand-rolled: the frontmatter we author is flat key/value with
    occasional folded blocks, and depending on PyYAML here would add a hard
    dependency for a 20-line problem.
    """
    match = _FRONTMATTER.match(raw)
    if not match:
        return {}, raw

    meta: dict[str, str] = {}
    key: str | None = None
    buffer: list[str] = []

    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        # A folded-block continuation is indented.
        if line.startswith((" ", "\t")) and key:
            buffer.append(line.strip())
            continue
        if key and buffer:
            meta[key] = " ".join(buffer).strip()
            buffer = []
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value in {">", "|", ">-", "|-"}:
                buffer = []
            else:
                meta[key] = value.strip("'\"")
                key = None

    if key and buffer:
        meta[key] = " ".join(buffer).strip()

    return meta, raw[match.end() :]


def parse_document(path: Path) -> ParsedDocument:
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    return ParsedDocument(path=path, frontmatter=meta, body=body)


def _split_long(text: str, size: int, overlap: int) -> list[str]:
    """Split an oversized section on paragraph boundaries, with overlap."""
    if len(text) <= size:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    pieces: list[str] = []
    current: list[str] = []
    length = 0

    for para in paragraphs:
        if length + len(para) > size and current:
            pieces.append("\n\n".join(current))
            # Carry the tail of the previous piece for continuity.
            tail = current[-1] if len(current[-1]) <= overlap else current[-1][-overlap:]
            current = [tail, para]
            length = len(tail) + len(para)
        else:
            current.append(para)
            length += len(para)

    if current:
        pieces.append("\n\n".join(current))
    return pieces


def chunk_document(doc: ParsedDocument) -> list[Chunk]:
    """Split a parsed document into heading-scoped chunks."""
    headings = list(_HEADING.finditer(doc.body))
    chunks: list[Chunk] = []

    if not headings:
        sections = [("Document", doc.body)]
    else:
        sections = []
        for index, match in enumerate(headings):
            title = match.group(2).strip()
            start = match.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(doc.body)
            sections.append((title, doc.body[start:end].strip()))

    counter = 0
    for section_title, section_text in sections:
        if len(section_text) < 40:  # skip bare headings with no substance
            continue
        for piece in _split_long(
            section_text, settings.rag_chunk_size, settings.rag_chunk_overlap
        ):
            counter += 1
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.document_id}#{counter:03d}",
                    # Prefixing the heading measurably improves embedding recall,
                    # because the section title carries most of the topic signal.
                    text=f"{doc.title} — {section_title}\n\n{piece}",
                    document_id=doc.document_id,
                    document_title=doc.title,
                    authority=doc.authority,
                    section=section_title,
                    source_path=str(doc.path.name),
                    hazard=doc.frontmatter.get("hazard", "all"),
                    phase=doc.frontmatter.get("phase", "response"),
                    provenance=doc.frontmatter.get("provenance", ""),
                )
            )

    return chunks


def load_knowledge_base(directory: Path | None = None) -> list[Chunk]:
    """Parse and chunk every document in the knowledge base."""
    root = directory or settings.knowledge_base_dir
    if not root.exists():
        logger.error("rag.kb_missing", path=str(root))
        return []

    all_chunks: list[Chunk] = []
    for path in sorted(root.glob("*.md")):
        try:
            doc = parse_document(path)
            doc_chunks = chunk_document(doc)
            all_chunks.extend(doc_chunks)
            logger.info(
                "rag.document_chunked",
                document=doc.document_id,
                chunks=len(doc_chunks),
            )
        except Exception as exc:  # noqa: BLE001 - one bad doc must not stop ingest
            logger.error("rag.document_failed", path=str(path), error=str(exc)[:200])

    return all_chunks
