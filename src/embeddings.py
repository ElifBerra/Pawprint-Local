"""Text -> vector, via the Foundry Local embedding client."""

from __future__ import annotations

import logging
from typing import List, Sequence

import numpy as np

from . import foundry

logger = logging.getLogger(__name__)

BATCH_SIZE = 16


def embed_texts(texts: Sequence[str]) -> np.ndarray:
    """Embed a list of texts. Returns shape (len(texts), dim), float32."""
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    client = foundry.get_embedding_client()
    vectors: List[List[float]] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = list(texts[start:start + BATCH_SIZE])
        logger.debug("Embedding batch %d-%d", start, start + len(batch))
        response = client.generate_embeddings(batch)
        # The API returns items in request order, but sort by index to be safe.
        items = sorted(response.data, key=lambda d: d.index)
        vectors.extend(item.embedding for item in items)

    return np.asarray(vectors, dtype=np.float32)


def embed_one(text: str) -> np.ndarray:
    """Embed a single text. Returns shape (dim,), float32."""
    client = foundry.get_embedding_client()
    response = client.generate_embedding(text)
    return np.asarray(response.data[0].embedding, dtype=np.float32)


def normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize row-wise so cosine similarity becomes a dot product."""
    if vectors.ndim == 1:
        norm = np.linalg.norm(vectors)
        return vectors / norm if norm else vectors
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms
