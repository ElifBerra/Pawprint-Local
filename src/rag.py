"""The RAG pipeline: retrieve, augment, generate."""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Sequence

from . import config, llm, retrieve
from .models import Answer, Chunk, Retrieved

logger = logging.getLogger(__name__)


def build_context(results: Sequence[Retrieved]) -> str:
    """Format retrieved chunks for the prompt, labelled by source."""
    return "\n\n".join(
        f"[{r.chunk.source}]\n{r.chunk.content}" for r in results
    )


def unique_sources(results: Sequence[Retrieved]) -> List[str]:
    """Source file names, best match first, no duplicates."""
    seen: List[str] = []
    for r in results:
        if r.chunk.source not in seen:
            seen.append(r.chunk.source)
    return seen


def answer(question: str, chunks: Optional[Sequence[Chunk]] = None) -> Answer:
    """Answer a question from the local document collection.

    Args:
        question: The user's question.
        chunks: Optional pre-loaded chunks, passed straight through to
            retrieval. Used by the tests.
    """
    started = time.perf_counter()

    if not question or not question.strip():
        return Answer(
            text="Please ask a question.",
            latency_s=time.perf_counter() - started,
            used_fallback=True,
        )

    results = retrieve.get_top_chunks(question, chunks=chunks)

    # Nothing close enough — don't call the model at all.
    if not retrieve.is_relevant(results):
        logger.info(
            "Below threshold (best=%.3f), returning fallback",
            results[0].score if results else 0.0,
        )
        return Answer(
            text=config.FALLBACK_ANSWER,
            retrieved=results,
            latency_s=time.perf_counter() - started,
            used_fallback=True,
        )

    system_prompt = config.SYSTEM_PROMPT.format(
        fallback=config.FALLBACK_ANSWER,
        context=build_context(results),
    )

    text = llm.generate(system_prompt, question)
    used_fallback = config.FALLBACK_ANSWER.lower() in text.lower()

    return Answer(
        text=text,
        sources=[] if used_fallback else unique_sources(results),
        retrieved=results,
        latency_s=time.perf_counter() - started,
        used_fallback=used_fallback,
    )
