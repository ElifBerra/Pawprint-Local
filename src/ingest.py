"""Build the knowledge base: documents -> chunks -> embeddings -> SQLite.

Run:  python -m src.ingest
      python -m src.ingest --rebuild     # start from an empty table
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List

from . import chunking, config, db, embeddings, foundry
from .models import Chunk

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".md", ".txt"}


def find_documents(docs_dir: Path = config.DOCS_DIR) -> List[Path]:
    """Every supported document in the docs directory, sorted."""
    if not docs_dir.exists():
        return []
    return sorted(
        p for p in docs_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def chunk_documents(paths: List[Path]) -> List[Chunk]:
    """Read and split every document."""
    chunks: List[Chunk] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        produced = chunking.split_document(text, source=path.name)
        print(f"  {path.name:<36} {len(text.split()):>6} words -> {len(produced):>3} chunks")
        chunks.extend(produced)
    return chunks


def embed_chunks(chunks: List[Chunk]) -> None:
    """Attach an embedding to every chunk, in place."""
    vectors = embeddings.embed_texts([c.content for c in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Pawprint knowledge base.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="delete existing chunks before ingesting",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="show debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    started = time.perf_counter()

    paths = find_documents()
    if not paths:
        print(f"No .md or .txt files found in {config.DOCS_DIR}")
        print("Add some documents there first.")
        sys.exit(1)

    print(f"\nFound {len(paths)} documents in {config.DOCS_DIR}\n")

    db.init_db()
    if args.rebuild:
        db.clear()

    print("Chunking:")
    chunks = chunk_documents(paths)
    if not chunks:
        print("\nDocuments produced no chunks. Are they empty?")
        sys.exit(1)

    print(f"\n{len(chunks)} chunks total. Generating embeddings...")
    embed_chunks(chunks)

    db.insert_chunks(chunks)
    foundry.unload_all()

    summary = db.stats()
    print(
        f"\nDone in {time.perf_counter() - started:.1f}s\n"
        f"  chunks   : {summary['chunks']}\n"
        f"  sources  : {summary['sources']}\n"
        f"  avg chars: {summary['avg_chars']}\n"
        f"  database : {config.DB_PATH}"
    )
    print("\nNow try:  python -m src.cli")


if __name__ == "__main__":
    main()
