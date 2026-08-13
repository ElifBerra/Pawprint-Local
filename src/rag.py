"""The RAG pipeline: retrieve, augment, generate.

Two shapes of answer:

  answer(question)              general questions against the document collection
  answer(question, pet=pet)     the same, plus the animal's own records

The second is what makes the assistant useful rather than merely correct. The
documents can say what a portion should be; only the records know what this
animal is actually being fed.
"""

from __future__ import annotations

import logging
import time
from typing import Generator, List, Optional, Sequence

from . import config, llm, pet_context, retrieve
from .models import Answer, Chunk, Pet, Retrieved

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
    pet: Optional[Pet] = None,
    lang: str = config.DEFAULT_LANGUAGE,
):
    """Shared front half of both answer paths: retrieve and build the prompt.

    Returns (results, system_prompt, used_pet). system_prompt is None when the
    question is out of scope and the model should not be called at all.
    """
    results = retrieve.get_top_chunks(
        question, k=config.TOP_K if k is None else k, chunks=chunks
    )

    use_pet = pet is not None and pet_context.has_useful_records(pet)

    # With records on file the bar is lower: "is Bella too heavy?" may match no
    # document strongly, yet the records answer it. Without records, a weak
    # match means we have nothing to say.
    relevant = retrieve.is_relevant(results, threshold=threshold)
    if not relevant and not use_pet:
        logger.info(
            "Below threshold (best=%.3f), returning fallback",
            results[0].score if results else 0.0,
        )
        return results, None, False

    language = config.LANGUAGE_INSTRUCTION.get(
        lang, config.LANGUAGE_INSTRUCTION["en"]
    )

    if use_pet:
        prompt = config.SYSTEM_PROMPT_WITH_PET.format(
            pet_context=pet_context.build(pet, lang),
            context=build_context(results) if relevant else "(no relevant passages)",
            fallback=config.fallback(lang),
            language=language,
        )
        return results if relevant else [], prompt, True

    prompt = config.SYSTEM_PROMPT.format(
        fallback=config.fallback(lang),
        context=build_context(results),
        language=language,
    )
    return results, prompt, False


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
    if not stripped:
        return True

    for phrase in config.FALLBACK_ANSWERS.values():
        lowered = phrase.lower()
        if lowered in stripped and len(stripped) <= len(lowered) * 4:
            return True
    return False


def answer(
    question: str,
    chunks: Optional[Sequence[Chunk]] = None,
    k: Optional[int] = None,
    threshold: Optional[float] = None,
    pet: Optional[Pet] = None,
    lang: str = config.DEFAULT_LANGUAGE,
) -> Answer:
    """Answer a question from the documents, and the animal's records if given.

    Args:
        question: The user's question.
        chunks: Optional pre-loaded chunks, passed to retrieval. Used by tests.
        k: Override for config.TOP_K.
        threshold: Override for config.SIM_THRESHOLD.
        pet: When given and records exist, the animal's data joins the prompt.
        lang: "en" or "tr" — the language of the answer.
    """
    started = time.perf_counter()

    if not question or not question.strip():
        return Answer(
            text="Please ask a question." if lang == "en" else "Lütfen bir soru yazın.",
            latency_s=time.perf_counter() - started,
            used_fallback=True,
        )

    results, system_prompt, used_pet = _prepare(
        question, chunks, k, threshold, pet, lang
    )

    if system_prompt is None:
        return Answer(
            text=config.fallback(lang),
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
        used_pet_record=used_pet and not used_fallback,
    )


def answer_stream(
    question: str,
    chunks: Optional[Sequence[Chunk]] = None,
    k: Optional[int] = None,
    threshold: Optional[float] = None,
    pet: Optional[Pet] = None,
    lang: str = config.DEFAULT_LANGUAGE,
) -> Generator[str, None, Answer]:
    """Same as answer(), but yields the text as it is generated.

    Total time is unchanged; what changes is that the first words appear in a
    couple of seconds instead of the reader watching a blank screen. Consume
    with a for loop and read the final Answer from StopIteration.value.
    """
    started = time.perf_counter()

    if not question or not question.strip():
        message = "Please ask a question." if lang == "en" else "Lütfen bir soru yazın."
        yield message
        return Answer(
            text=message,
            latency_s=time.perf_counter() - started,
            used_fallback=True,
        )

    results, system_prompt, used_pet = _prepare(
        question, chunks, k, threshold, pet, lang
    )

    if system_prompt is None:
        yield config.fallback(lang)
        return Answer(
            text=config.fallback(lang),
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
        used_pet_record=used_pet and not used_fallback,
    )
