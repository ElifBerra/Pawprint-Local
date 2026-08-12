"""The RAG pipeline: retrieve, augment, generate."""

from __future__ import annotations

import logging
import time
from typing import Generator, List, Optional, Sequence

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


def _prepare(
    question: str,
    chunks: Optional[Sequence[Chunk]],
    k: Optional[int] = None,
    threshold: Optional[float] = None,
):
    """Shared front half of both answer paths: retrieve and build the prompt.

    Returns (results, system_prompt). system_prompt is None when the question
    is out of scope and the model should not be called at all.
    """
    results = retrieve.get_top_chunks(
        question, k=config.TOP_K if k is None else k, chunks=chunks
    )

    if not retrieve.is_relevant(results, threshold=threshold):
        logger.info(
            "Below threshold (best=%.3f), returning fallback",
            results[0].score if results else 0.0,
        )
        return results, None

    prompt = config.SYSTEM_PROMPT.format(
        fallback=config.FALLBACK_ANSWER,
        context=build_context(results),
    )
    return results, prompt


def answer_stream(
    question: str,
    chunks: Optional[Sequence[Chunk]] = None,
    k: Optional[int] = None,
    threshold: Optional[float] = None,
) -> Generator[str, None, Answer]:
    """Same as answer(), but yields the text as it is generated.

    Total time is unchanged; what changes is that the first words appear in a
    couple of seconds instead of the reader watching a blank screen. Consume
    with a for loop and read the final Answer from StopIteration.value, or use
    the helper in cli.py.
    """
    started = time.perf_counter()

    if not question or not question.strip():
        yield "Please ask a question."
        return Answer(
            text="Please ask a question.",
            latency_s=time.perf_counter() - started,
            used_fallback=True,
        )

    results, system_prompt = _prepare(question, chunks, k, threshold)

    if system_prompt is None:
        yield config.FALLBACK_ANSWER
        return Answer(
            text=config.FALLBACK_ANSWER,
            retrieved=results,
            latency_s=time.perf_counter() - started,
            used_fallback=True,
        )

    pieces: List[str] = []
    for piece in llm.generate_streaming(system_prompt, question):
        pieces.append(piece)
        yield piece

    text = "".join(pieces).strip()
    used_fallback = _is_fallback(text)

    return Answer(
        text=text,
        sources=[] if used_fallback else unique_sources(results),
        retrieved=results,
        latency_s=time.perf_counter() - started,
        used_fallback=used_fallback,
    )


def _is_fallback(text: str) -> bool:
    """Whether the model declined to answer.

    Two failure modes pull in opposite directions and this has to sit between
    them:

    - Requiring an exact match is too strict. The model often prefixes the
      refusal: "I'm sorry, but the provided context does not contain
      information regarding X. I don't have that information in my documents."
      That is a correct refusal and the evaluation scored three of them as
      failures before this was widened.
    - Accepting the phrase anywhere is too loose. Earlier the model emitted the
      refusal and then answered anyway, and a plain substring test hid the
      sources of a real answer.

    So: the phrase must be present and the reply must stay short. A refusal
    with an apology runs to roughly three times the phrase; a refusal followed
    by a smuggled answer runs much longer.
    """
    stripped = text.strip().strip('"').strip().lower()
    fallback = config.FALLBACK_ANSWER.lower()

    if not stripped:
        return True
    if fallback not in stripped:
        return False
    return len(stripped) <= len(fallback) * 4


def answer(
    question: str,
    chunks: Optional[Sequence[Chunk]] = None,
    k: Optional[int] = None,
    threshold: Optional[float] = None,
) -> Answer:
    """Answer a question from the local document collection.

    Args:
        question: The user's question.
        chunks: Optional pre-loaded chunks, passed straight through to
            retrieval. Used by the tests.
        k: Override for config.TOP_K.
        threshold: Override for config.SIM_THRESHOLD.
    """
    started = time.perf_counter()

    if not question or not question.strip():
        return Answer(
            text="Please ask a question.",
            latency_s=time.perf_counter() - started,
            used_fallback=True,
        )

    results, system_prompt = _prepare(question, chunks, k, threshold)

    # Nothing close enough — don't call the model at all.
    if system_prompt is None:
        return Answer(
            text=config.FALLBACK_ANSWER,
            retrieved=results,
            latency_s=time.perf_counter() - started,
            used_fallback=True,
        )

    text = llm.generate(system_prompt, question)
    used_fallback = _is_fallback(text)

    return Answer(
        text=text,
        sources=[] if used_fallback else unique_sources(results),
        retrieved=results,
        latency_s=time.perf_counter() - started,
        used_fallback=used_fallback,
    )
