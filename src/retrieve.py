"""Semantic search over the stored chunks.

Brute-force cosine similarity. With a few hundred chunks this is a single
matrix multiply and takes under a millisecond, so a vector index would be
premature. See docs/ARCHITECTURE.md for where that stops being true.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

import numpy as np

from . import config, embeddings
from .models import Chunk, Retrieved

logger = logging.getLogger(__name__)

# Cache of the query vector for repeated identical questions.
_query_cache: dict[str, np.ndarray] = {}


def rank(query_vector: np.ndarray, chunks: Sequence[Chunk]) -> List[Retrieved]:
    """Score every chunk against the query vector, best first."""
    if not chunks:
        return []

    matrix = np.vstack([c.embedding for c in chunks]).astype(np.float32)
    scores = embeddings.normalize(matrix) @ embeddings.normalize(query_vector)

    order = np.argsort(-scores)
    return [Retrieved(chunk=chunks[i], score=float(scores[i])) for i in order]


def embed_query(query: str) -> np.ndarray:
    """Embed a query, reusing the vector if we have seen it before."""
    key = query.strip().lower()
    if key not in _query_cache:
        _query_cache[key] = embeddings.embed_one(query)
    return _query_cache[key]


def expand(query: str, terms: Optional[str]) -> str:
    """Add the animal's own context to a question before embedding it.

    People leave out what is obvious to them. "Can I give chocolate?" scores
    0.446 against the collection and falls below the threshold; the same
    question written out as "can I give my cat chocolate" scores 0.523. The
    missing signal is the species — which the profile already knows.

    This is completing the question, not rewriting it. The user is asking
    about their animal; the prompt still receives what they actually typed.
    """
    if not terms:
        return query
    return f"{query.strip()} ({terms})"


def get_top_chunks(
    query: str,
    k: int = config.TOP_K,
    chunks: Optional[Sequence[Chunk]] = None,
    context_terms: Optional[str] = None,
) -> List[Retrieved]:
    """Return the k best-matching chunks for a query.

    Args:
        query: The user's question.
        k: How many chunks to return.
        chunks: Optional pre-loaded chunks. When omitted they are read from
            the database. Passing them in keeps the tests free of I/O.
        context_terms: Words describing the animal, folded into the text that
            is embedded. Does not change the question the model is shown.
    """
    if not query or not query.strip():
        return []

    query = expand(query, context_terms)

    if chunks is None:
        from . import db  # imported lazily so tests can skip the database
        chunks = db.load_all_chunks()

    if not chunks:
        logger.warning("No chunks in the database. Run: python -m src.ingest")
        return []

    results = rank(embed_query(query), chunks)[:k]
    logger.debug(
        "Query %r -> %s", query, [(r.chunk.source, round(r.score, 3)) for r in results]
    )
    return results


def is_relevant(
    results: Sequence[Retrieved],
    threshold: Optional[float] = None,
) -> bool:
    """Whether the best match clears the similarity threshold.

    Below it we treat the question as out of scope and skip the model
    entirely: faster, and it removes any chance of the model inventing an
    answer from a weak match.

    Args:
        results: Ranked chunks, best first.
        threshold: Override for config.SIM_THRESHOLD. The Streamlit sidebar
            uses this so the threshold can be explored without a restart.
    """
    limit = config.SIM_THRESHOLD if threshold is None else threshold
    return bool(results) and results[0].score >= limit
