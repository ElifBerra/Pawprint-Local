"""Shared data types.

This is the contract between the ingestion side (chunking, db, ingest) and
the query side (retrieve, rag, cli). Both halves import from here, so they can
be built independently as long as these shapes hold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class Chunk:
    """A passage of a source document, with its embedding."""

    source: str          # file name, e.g. "vaccination.md"
    chunk_index: int     # position within that file, 0-based
    content: str
    embedding: Optional[np.ndarray] = None   # float32, shape (dim,)
    id: Optional[int] = None                 # set by the database


@dataclass
class Retrieved:
    """A chunk plus how well it matched the query."""

    chunk: Chunk
    score: float


@dataclass
class Answer:
    """The result of a full RAG round trip."""

    text: str
    sources: List[str] = field(default_factory=list)
    retrieved: List[Retrieved] = field(default_factory=list)
    latency_s: float = 0.0
    used_fallback: bool = False
