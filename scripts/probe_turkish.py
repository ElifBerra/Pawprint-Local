"""Compare two ways of getting Turkish answers out of an English collection.

A: an English prompt with "write the answer in Turkish" appended.
B: a prompt written in Turkish throughout, retrieved passages still English.

The probe that motivated this showed A producing broken sentences while a
short all-Turkish prompt produced clean ones. This measures the difference on
real questions rather than on one example.

Run:  python -m scripts.probe_turkish
"""

from __future__ import annotations

import statistics
import time
from typing import List

from src import config, foundry, llm, pet_context, pets_db, rag

QUESTIONS = [
    ("Yavru köpeğin aşı takvimi nasıl olmalı?", False),
    ("Kedime köpeğin pire ilacını sürebilir miyim?", False),
    ("Köpeğime çikolata verebilir miyim?", False),
    ("Bella kilo alıyor, porsiyonu azaltmalı mıyım?", True),
    ("Bella'nın kilosu hedefin neresinde?", True),
]

# The previous approach, kept here so the comparison is honest rather than
# reconstructed from memory.
OLD_INSTRUCTION = (
    "Cevabı Türkçe yaz. Kaynak belgeler İngilizce; bilgiyi Türkçeye çevirerek "
    "aktar, İngilizce cümle bırakma."
)


def english_prompt_with_instruction(question: str, pet, use_pet: bool) -> str:
    """Rebuild variant A."""
    results = rag.retrieve.get_top_chunks(question)
    context = rag.build_context(results)
    if use_pet and pet is not None:
        return config.SYSTEM_PROMPT_WITH_PET.format(
            pet_context=pet_context.build(pet, "tr"),
            context=context,
            fallback=config.fallback("tr"),
            language=OLD_INSTRUCTION,
        )
    return config.SYSTEM_PROMPT.format(
        fallback=config.fallback("tr"),
        context=context,
        language=OLD_INSTRUCTION,
    )


def looks_english(text: str) -> bool:
    """Rough check for untranslated leftovers."""
    markers = (" the ", " and ", " weight ", " should ", " your ", " with ")
    lowered = f" {text.lower()} "
    return sum(1 for m in markers if m in lowered) >= 2


def run(label: str, prompts, questions) -> List[float]:
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
    latencies: List[float] = []

    for (question, use_pet), prompt in zip(questions, prompts):
        started = time.perf_counter()
        try:
            text = llm.generate(prompt, question)
        except Exception as exc:
            print(f"\nQ: {question}\n   FAILED {type(exc).__name__}: {exc}")
            continue
        elapsed = time.perf_counter() - started
        latencies.append(elapsed)

        flag = "  <-- English leaked through" if looks_english(text) else ""
        print(f"\nQ: {question}   [{elapsed:.1f}s]{' (records)' if use_pet else ''}")
        print(f"A: {' '.join(text.split())}{flag}")

    return latencies


def main() -> None:
    pet = pets_db.first_pet()
    if pet is None:
        print("No pet found. Run: python -m scripts.seed_demo --reset")
        return

    print("Loading models...")
    foundry.get_chat_client()
    foundry.get_embedding_client()

    prompts_a = [
        english_prompt_with_instruction(q, pet, use_pet)
        for q, use_pet in QUESTIONS
    ]
    prompts_b = []
    for question, use_pet in QUESTIONS:
        _, prompt, _ = rag._prepare(
            question, None, None, None, pet if use_pet else None, "tr"
        )
        prompts_b.append(prompt)

    a = run("A — English prompt + 'write in Turkish'", prompts_a, QUESTIONS)
    b = run("B — prompt written in Turkish", prompts_b, QUESTIONS)

    print(f"\n{'=' * 72}")
    if a:
        print(f"A median latency: {statistics.median(a):.1f}s")
    if b:
        print(f"B median latency: {statistics.median(b):.1f}s")
    print("\nJudge the answers yourself: fluency, correct numbers, no English.")

    foundry.unload_all()


if __name__ == "__main__":
    main()
