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
        question,
        k=config.TOP_K if k is None else k,
        chunks=chunks,
        context_terms=pet_context.search_terms(pet),
    )

    use_pet = pet is not None and pet_context.has_useful_records(pet)

    # The threshold is per-language: the documents are English, so a Turkish
    # question is matched across languages and scores about 0.30 lower for the
    # same meaning. See config.SIM_THRESHOLDS.
    limit = config.threshold(lang) if threshold is None else threshold

    # With records on file the bar is lower: "is Bella too heavy?" may match no
    # document strongly, yet the records answer it. Without records, a weak
    # match means we have nothing to say.
    relevant = retrieve.is_relevant(results, threshold=limit)
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
        # No passage cleared the threshold. Before falling back on the records,
        # check the question is even about them — otherwise the model gets
        # called for something neither source covers and answers from memory.
        if not relevant:
            score = pet_context.relevance(
                pet, retrieve.embed_query(question), lang
            )
            logger.info("Records relevance %.3f (limit %.2f)",
                        score, config.pet_threshold(lang))

            if score < config.pet_threshold(lang):
                return results, None, False

            prompt = config.system_prompt(lang, records_only=True).format(
                pet_context=pet_context.build(pet, lang),
                fallback=config.fallback(lang),
                language=language,
            )
            # The chunks are kept so the interface can still show what was
            # looked at and how far short it fell; they are simply not in the
            # prompt.
            return results, prompt, True

        prompt = config.system_prompt(lang, with_pet=True).format(
            pet_context=pet_context.build(pet, lang),
            context=build_context(results),
            fallback=config.fallback(lang),
            language=language,
        )
        return results, prompt, True

    prompt = config.system_prompt(lang, with_pet=False).format(
        fallback=config.fallback(lang),
        context=build_context(results),
        language=language,
    )
    return results, prompt, False


def strip_spurious_fallback(text: str) -> str:
    """Remove the refusal sentence when the model also answered.

    The model sometimes opens with "I don't have that information in my
    documents" and then answers anyway, from passages that were retrieved and
    are cited underneath. The refusal is not true — the sources are right
    there — and leaving it in makes the assistant contradict itself in its own
    first line.

    The phrase is a control token, not prose. If substantive content follows
    it, the refusal is spurious and comes out.
    """
    if _is_fallback(text):
        return text

    cleaned = text
    for phrase in config.FALLBACK_ANSWERS.values():
        for variant in (phrase, phrase.rstrip("."), f'"{phrase}"'):
            index = cleaned.lower().find(variant.lower())
            if index == -1:
                continue
            cleaned = (cleaned[:index] + cleaned[index + len(variant):])

    # Tidy what the removal left behind: a leading connective, stray
    # punctuation, or a doubled space.
    cleaned = cleaned.strip().lstrip('."” ').strip()
    for opener in ("However, ", "However ", "Ancak, ", "Ancak ", "But "):
        if cleaned.startswith(opener):
            cleaned = cleaned[len(opener):]
            cleaned = cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
            break

    return cleaned or text


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
    if not used_fallback:
        text = strip_spurious_fallback(text)

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
    on_retrieved=None,
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

    # Retrieval finishes in well under a second; generation takes fifteen, and
    # about eighty per cent of that is the model reading the prompt before it
    # writes anything. Handing the passages over now lets the interface show
    # what was found while the model is still thinking, instead of a blank
    # panel — and what it shows is the retrieval step doing its job.
    if on_retrieved is not None:
        on_retrieved(results, used_pet)

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
    if not used_fallback:
        # The stream already showed the refusal; the final Answer carries the
        # cleaned text and the interface replaces what it displayed with it.
        text = strip_spurious_fallback(text)

    return Answer(
        text=text,
        sources=[] if used_fallback else unique_sources(results),
        retrieved=results,
        latency_s=time.perf_counter() - started,
        used_fallback=used_fallback,
        used_pet_record=used_pet and not used_fallback,
    )
