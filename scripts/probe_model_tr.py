"""Measure a candidate model's Turkish output on the real prompts.

phi-3.5-mini failed this: broken grammar, 45-85s per answer, and frequent
"Operation was cancelled" on longer generations. Turkish splits into many more
tokens in its vocabulary than English does, so every Turkish answer is both
slower and further outside what the model was trained on.

Run:  python -m scripts.probe_model_tr --model qwen3-1.7b
      python -m scripts.probe_model_tr --model qwen3-4b --max-tokens 200
"""

from __future__ import annotations

import argparse
import statistics
import time
from typing import List

from src import config, foundry, pet_context, pets_db, rag

QUESTIONS = [
    ("Yavru köpeğin aşı takvimi nasıl olmalı?", False,
     ["altı", "sekiz", "hafta", "on altı"]),
    ("Kedime köpeğin pire ilacını sürebilir miyim?", False,
     ["hayır", "permethrin", "toksik", "zehirli", "kullanma"]),
    ("Köpeğime çikolata verebilir miyim?", False,
     ["hayır", "teobromin", "toksik", "zehirli"]),
    ("Bella kilo alıyor, porsiyonu azaltmalı mıyım?", True,
     ["2,5", "2.5", "2,0", "2.0", "bardak"]),
    ("Bella'nın kilosu hedefin neresinde?", True,
     ["30,2", "30.2", "28", "üzerinde"]),
]


def hits(text: str, expected: List[str]) -> List[str]:
    lowered = text.lower()
    return [e for e in expected if e.lower() in lowered]


def looks_english(text: str) -> bool:
    markers = (" the ", " and ", " weight ", " should ", " your ", " with ")
    lowered = f" {text.lower()} "
    return sum(1 for m in markers if m in lowered) >= 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=config.CHAT_MODEL_ALIAS,
                        help="chat model alias to test")
    parser.add_argument("--max-tokens", type=int, default=config.MAX_TOKENS)
    args = parser.parse_args()

    pet = pets_db.first_pet()
    if pet is None:
        print("No pet found. Run: python -m scripts.seed_demo --reset")
        return

    # Point the wrapper at the candidate before anything loads.
    config.CHAT_MODEL_ALIAS = args.model
    config.MAX_TOKENS = args.max_tokens

    print(f"Model      : {args.model}")
    print(f"max_tokens : {args.max_tokens}")
    print("Loading (first run downloads the model)...\n")

    foundry.get_embedding_client()
    client = foundry.get_chat_client()

    latencies: List[float] = []
    failures = 0
    english_leaks = 0
    total_hits = 0
    total_expected = 0

    for question, use_pet, expected in QUESTIONS:
        _, prompt, _ = rag._prepare(
            question, None, None, None, pet if use_pet else None, "tr"
        )
        if prompt is None:
            print(f"Q: {question}\n   below threshold, no model call\n")
            continue

        started = time.perf_counter()
        try:
            response = client.complete_chat([
                {"role": "system", "content": prompt},
                {"role": "user", "content": question},
            ])
            text = " ".join((response.choices[0].message.content or "").split())
        except Exception as exc:
            failures += 1
            print(f"Q: {question}\n   FAILED {type(exc).__name__}: {str(exc)[:80]}\n")
            continue

        elapsed = time.perf_counter() - started
        latencies.append(elapsed)

        found = hits(text, expected)
        total_hits += len(found)
        total_expected += len(expected)
        leaked = looks_english(text)
        english_leaks += int(leaked)

        print(f"Q: {question}   [{elapsed:.1f}s]{'  (records)' if use_pet else ''}")
        print(f"A: {text[:400]}")
        print(f"   key terms: {len(found)}/{len(expected)} {found}"
              f"{'   ENGLISH LEAK' if leaked else ''}\n")

    print("=" * 72)
    print(f"Model          : {args.model}")
    print(f"Failures       : {failures}/{len(QUESTIONS)}")
    print(f"English leaks  : {english_leaks}")
    print(f"Key term recall: {total_hits}/{total_expected}")
    if latencies:
        print(f"Median latency : {statistics.median(latencies):.1f}s")
        print(f"Max latency    : {max(latencies):.1f}s")
    print("\nKey-term recall is a rough proxy. Read the answers before deciding.")

    foundry.unload_all()


if __name__ == "__main__":
    main()
