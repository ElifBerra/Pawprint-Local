"""SQLite storage for chunks and their embeddings.

Embeddings are stored as raw float32 BLOBs rather than JSON: about four times
smaller and it skips parsing on every read, which matters because retrieval
loads the whole table on each query.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from typing import Iterator, List, Sequence

import numpy as np

from . import config
from .models import Chunk

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT    NOT NULL,
    chunk_index  INTEGER NOT NULL,
    content      TEXT    NOT NULL,
    embedding    BLOB    NOT NULL,
    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open the database, commit on success, always close."""
    conn = sqlite3.connect(config.DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create the schema if it is not already there."""
    with connect() as conn:
        conn.executescript(SCHEMA)
    logger.info("Database ready at %s", config.DB_PATH)


def insert_chunks(chunks: Sequence[Chunk]) -> int:
    """Store chunks with their embeddings.

    UNIQUE(source, chunk_index) plus INSERT OR REPLACE means re-ingesting a
    document updates its rows instead of duplicating them.
    """
    if not chunks:
        return 0

    rows = []
    for chunk in chunks:
        if chunk.embedding is None:
            raise ValueError(
                f"Chunk {chunk.source}#{chunk.chunk_index} has no embedding."
            )
        blob = np.asarray(chunk.embedding, dtype=np.float32).tobytes()
        rows.append((chunk.source, chunk.chunk_index, chunk.content, blob))

    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO chunks (source, chunk_index, content, embedding) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )

    logger.info("Stored %d chunks", len(rows))
    return len(rows)


def load_all_chunks() -> List[Chunk]:
    """Every chunk, embeddings decoded back into numpy arrays."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, source, chunk_index, content, embedding FROM chunks "
            "ORDER BY source, chunk_index"
        ).fetchall()

    return [
        Chunk(
            id=row[0],
            source=row[1],
            chunk_index=row[2],
            content=row[3],
            embedding=np.frombuffer(row[4], dtype=np.float32),
        )
        for row in rows
    ]


def clear() -> None:
    """Delete every row. Used by ingest --rebuild."""
    with connect() as conn:
        conn.execute("DELETE FROM chunks")
    logger.info("Cleared all chunks")


def count() -> int:
    """How many chunks are stored."""
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]


def sources() -> List[str]:
    """Distinct source file names."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT source FROM chunks ORDER BY source"
        ).fetchall()
    return [row[0] for row in rows]


def stats() -> dict:
    """Small summary for the CLI and the Streamlit sidebar."""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT source), "
            "COALESCE(AVG(LENGTH(content)), 0) FROM chunks"
        ).fetchone()
    return {
        "chunks": row[0],
        "sources": row[1],
        "avg_chars": round(row[2]),
    }
