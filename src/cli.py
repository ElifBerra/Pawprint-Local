"""Command-line interface for Pawprint-Local.

Run:  python -m src.cli
"""

from __future__ import annotations

import logging
import sys

from . import config, foundry, rag
from .models import Answer

BANNER = """
Pawprint-Local - offline pet health assistant
Ask a question about the documents in data/docs.
Commands: /sources  /help  /exit
"""

HELP = """
/sources   show the passages behind the last answer
/help      this message
/exit      quit
"""

DISCLAIMER = "This is not veterinary advice. See a vet for anything urgent."


def stream_answer(question: str) -> Answer:
    """Print the answer as it arrives, then return the finished Answer."""
    print()
    generator = rag.answer_stream(question)
    while True:
        try:
            print(next(generator), end="", flush=True)
        except StopIteration as stop:
            print()
            return stop.value


def print_footer(result: Answer) -> None:
    if result.sources:
        print(f"\nSources: {', '.join(result.sources)}")
    print(f"[{result.latency_s:.1f}s]")
    if not result.used_fallback:
        print(DISCLAIMER)


def print_sources(result: Answer | None) -> None:
    if result is None or not result.retrieved:
        print("\nNothing retrieved yet.")
        return
    print()
    for r in result.retrieved:
        preview = r.chunk.content.strip().replace("\n", " ")
        if len(preview) > 300:
            preview = preview[:300] + "..."
        print(f"  {r.score:.3f}  {r.chunk.source} #{r.chunk.chunk_index}")
        print(f"         {preview}\n")


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not config.DB_PATH.exists():
        print(f"No database at {config.DB_PATH}.")
        print("Run this first:  python -m src.ingest")
        sys.exit(1)

    print(BANNER)
    print("Loading models (first run downloads them)...")
    foundry.get_chat_client()
    foundry.get_embedding_client()
    print("Ready.\n")

    last: Answer | None = None

    try:
        while True:
            try:
                question = input("you > ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not question:
                continue
            if question in ("/exit", "/quit"):
                break
            if question == "/help":
                print(HELP)
                continue
            if question == "/sources":
                print_sources(last)
                continue

            last = stream_answer(question)
            print_footer(last)
            print()
    finally:
        print("\nUnloading models...")
        foundry.unload_all()
        print("Bye.")


if __name__ == "__main__":
    main()
