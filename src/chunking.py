"""Splitting documents into passages for retrieval.

Chunk size is the single most influential knob in this project: too small and a
passage loses the context that makes it meaningful, too large and the embedding
averages out into something that matches everything weakly. Paragraphs are kept
whole wherever possible, since the author already grouped related sentences.
"""

from __future__ import annotations

import re
from typing import List

from . import config
from .models import Chunk

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def split_paragraphs(text: str) -> List[str]:
    """Split on blank lines, dropping empties."""
    return [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]


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


def split_document(
    text: str,
    source: str,
    chunk_size: int = config.CHUNK_SIZE,
    overlap: int = config.CHUNK_OVERLAP,
) -> List[Chunk]:
    """Split one document into overlapping chunks.

    Args:
        text: Full document text.
        source: File name, stored with each chunk so answers can cite it.
        chunk_size: Target words per chunk.
        overlap: Words carried from the end of one chunk into the next, so a
            fact spanning a boundary is not lost to both sides.

    Returns:
        Chunks with ``chunk_index`` counting from 0 and ``embedding`` unset —
        ingestion fills that in.
    """
    if not text or not text.strip():
        return []

    # An overlap at or above chunk_size would never advance.
    overlap = max(0, min(overlap, chunk_size // 2))

    units = _to_units(split_paragraphs(text), chunk_size)

    grouped: List[List[str]] = []
    current: List[str] = []

    for unit in units:
        if current and len(current) + len(unit) > chunk_size:
            grouped.append(current)
            current = current[-overlap:] if overlap else []
        current.extend(unit)

    if current:
        grouped.append(current)

    return [
        Chunk(source=source, chunk_index=i, content=" ".join(words))
        for i, words in enumerate(grouped)
    ]
