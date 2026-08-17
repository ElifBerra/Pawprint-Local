"""Latency and behaviour benchmark.

Runs a fixed set of questions and reports timing, so configuration changes can
be compared rather than guessed at. Numbers go into docs/EVALUATION.md.

Run:  python -m scripts.bench
"""

import argparse
import statistics
import time

from src import config, db, foundry, pet_context, pets_db, rag

QUESTIONS = [
    "How often does my puppy need vaccinations?",
    "My cat is straining in the litter box, is that urgent?",
    "Can I give my dog chocolate?",
    "How do I remove a tick?",
    "Why does my dog have bad breath?",
    "How often should I feed a kitten?",
    "What is the capital of France?",          # out of scope
    "Who won the World Cup in 1998?",          # out of scope
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-pet", action="store_true",
                        help="ignore the animal's records, to isolate their cost")
    args = parser.parse_args()

    # The web interface always passes the pet, so a benchmark that leaves it out
    # measures a path nobody uses. --no-pet exists to price the difference.
    pet = None if args.no_pet else pets_db.first_pet()

    stats = db.stats()
    print(
        f"Config: chunk_size={config.CHUNK_SIZE} overlap={config.CHUNK_OVERLAP} "
        f"top_k={config.TOP_K} max_tokens={config.MAX_TOKENS} "
        f"threshold={config.SIM_THRESHOLD}"
    )
    print(f"Corpus: {stats['chunks']} chunks from {stats['sources']} sources "
          f"(avg {stats['avg_chars']} chars)")

    if pet is not None:
        context = pet_context.build(pet, "en")
        print(f"Pet: {pet.name} — context {len(context)} chars, "
              f"{len(context.split())} words")
    else:
        print("Pet: none (records excluded)")
    print()

    print("Warming up models...")
    warm = time.perf_counter()
    foundry.get_chat_client()
    foundry.get_embedding_client()
    print(f"Warm-up: {time.perf_counter() - warm:.1f}s\n")

    latencies = []
    fallbacks = 0

    errors = 0

    for question in QUESTIONS:
        try:
            result = rag.answer(question, pet=pet)
        except Exception as exc:
            errors += 1
            print(f"[ ERROR ] {question}\n  {type(exc).__name__}: {exc}\n")
            continue

        latencies.append(result.latency_s)
        if result.used_fallback:
            fallbacks += 1

        top = result.retrieved[0].score if result.retrieved else 0.0
        flag = "FALLBACK" if result.used_fallback else "answered"
        preview = " ".join(result.text.split())[:100]

        print(f"[{result.latency_s:6.1f}s] [top={top:.3f}] [{flag}]")
        print(f"  Q: {question}")
        print(f"  A: {preview}{'...' if len(result.text) > 100 else ''}")
        print(f"  S: {', '.join(result.sources) or '-'}\n")

    print("=" * 60)
    print(f"Questions   : {len(QUESTIONS)}")
    print(f"Errors      : {errors}")
    print(f"Fallbacks   : {fallbacks}  (2 expected)")
    if latencies:
        print(f"Mean        : {statistics.mean(latencies):.1f}s")
        print(f"Median      : {statistics.median(latencies):.1f}s")
        print(f"Min / Max   : {min(latencies):.1f}s / {max(latencies):.1f}s")

    foundry.unload_all()


if __name__ == "__main__":
    main()
