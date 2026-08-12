"""Splitting documents into passages for retrieval.

Chunk size is the most influential knob in this project: too small and a passage
loses the context that makes it meaningful, too large and the embedding averages
out into something that matches everything weakly.

Two structural rules keep chunks on a single topic:

1. Chunks never cross a Markdown heading. The author already grouped related
   material under headings, and merging across one produces a chunk about two
   subjects. That caused a real failure — a question about chocolate returned an
   answer that also claimed chocolate indicates kidney disease and diabetes,
   because the "dangerous foods" and "water intake" sections had been packed
   into one chunk.
2. Each chunk carries its heading trail, so a passage reading "Chocolate
   contains theobromine" still says which document and section it belongs to.
   This also gives the embedding model useful signal.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from . import config
from .models import Chunk

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def split_paragraphs(text: str) -> List[str]:
    """Split on blank lines, dropping empties."""
    return [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]


def split_sections(text: str) -> List[Tuple[str, str]]:
    """Split a Markdown document into (heading trail, body) pairs.

    The heading trail joins ancestors with " > ", so a level-2 heading under a
    level-1 title reads "Nutrition and Feeding > Foods that are dangerous".
    Text before any heading is returned with an empty trail.
    """
    sections: List[Tuple[str, str]] = []
    stack: List[Tuple[int, str]] = []
    trail = ""
    body: List[str] = []

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            sections.append((trail, content))
        body.clear()

    for line in text.splitlines():
        match = _HEADING.match(line)
        if not match:
            body.append(line)
            continue

        flush()
        level = len(match.group(1))
        title = match.group(2).strip()

        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        trail = " > ".join(t for _, t in stack)

    flush()
    return sections


def _to_units(paragraphs: List[str], chunk_size: int) -> List[List[str]]:
    """Paragraphs as word lists. Oversized ones are cut into windows."""
    units: List[List[str]] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            continue
        if len(words) <= chunk_size:
            units.append(words)
        else:
            for start in range(0, len(words), chunk_size):
                units.append(words[start:start + chunk_size])
    return units


def _pack(units: List[List[str]], chunk_size: int, overlap: int) -> List[str]:
    """Greedily group word-lists into chunks of at most chunk_size words."""
    grouped: List[List[str]] = []
    current: List[str] = []

    for unit in units:
        if current and len(current) + len(unit) > chunk_size:
            grouped.append(current)
            current = current[-overlap:] if overlap else []
        current.extend(unit)

    if current:
        grouped.append(current)

    return [" ".join(words) for words in grouped]


def split_document(
    text: str,
    source: str,
    chunk_size: int = config.CHUNK_SIZE,
    overlap: int = config.CHUNK_OVERLAP,
) -> List[Chunk]:
    """Split one document into heading-bounded, overlapping chunks.

    Args:
        text: Full document text.
        source: File name, stored with each chunk so answers can cite it.
        chunk_size: Target words per chunk, excluding the heading trail.
        overlap: Words carried between chunks within the same section, so a fact
            spanning a boundary is not lost to both sides. Overlap never crosses
            a heading.

    Returns:
        Chunks with ``chunk_index`` counting from 0 across the whole document,
        and ``embedding`` unset — ingestion fills that in.
    """
    if not text or not text.strip():
        return []

    # An overlap at or above chunk_size would never advance.
    overlap = max(0, min(overlap, chunk_size // 2))

    chunks: List[Chunk] = []

    for trail, body in split_sections(text):
        units = _to_units(split_paragraphs(body), chunk_size)
        for piece in _pack(units, chunk_size, overlap):
            content = f"{trail}\n\n{piece}" if trail else piece
            chunks.append(
                Chunk(source=source, chunk_index=len(chunks), content=content)
            )

    return chunks
