"""Measure how much retrieval loses when the question and the documents differ
in language.

The collection is English. qwen3-embedding-0.6b is multilingual, so a Turkish
question does land near the right English passage — but the similarity score is
systematically lower than for the same question asked in English. Since the
relevance threshold is a single number tuned on English, Turkish questions fall
below it and are refused before the model is ever called.

This pairs each Turkish question with its English equivalent and reports both,
so the gap can be measured rather than guessed at.

Run:  python -m scripts.probe_crosslingual
"""

from __future__ import annotations

import statistics
from typing import List, Tuple

from src import config, foundry, retrieve

# (Turkish, English, document that should be retrieved)
PAIRS: List[Tuple[str, str, str]] = [
    ("Yavru köpeğin aşı takvimi nasıl olmalı?",
     "What vaccination schedule does a puppy need?",
     "vaccination-schedule.md"),
    ("Kedime köpeğin pire ilacını sürebilir miyim?",
     "Can I use my dog's flea treatment on my cat?",
     "parasite-prevention.md"),
    ("Köpeğime çikolata verebilir miyim?",
     "Can I give my dog chocolate?",
     "nutrition-and-feeding.md"),
    ("Kedim kum kabında zorlanıyor, acil mi?",
     "My cat is straining in the litter box, is that urgent?",
     "emergency-signs.md"),
    ("Köpeğimin nefesi neden kötü kokuyor?",
     "Why does my dog have bad breath?",
     "dental-and-grooming.md"),
    ("Kediye ne sıklıkla mama verilmeli?",
     "How often should I feed a kitten?",
     "nutrition-and-feeding.md"),
    ("Yetişkin köpeğe ne sıklıkla solucan ilacı verilir?",
     "How often should I worm an adult dog?",
     "parasite-prevention.md"),
    ("Köpeğime kendi diş macunumu kullanabilir miyim?",
     "Can I brush my dog's teeth with my own toothpaste?",
     "dental-and-grooming.md"),
    # Out of scope in both languages, to check the floor moves the same way.
    ("Köpeğime oturmayı nasıl öğretirim?",
     "How do I train my puppy to sit?",
     None),
    ("Fransa'nın başkenti neresi?",
     "What is the capital of France?",
     None),
]


def measure(question: str) -> Tuple[float, List[str]]:
    results = retrieve.get_top_chunks(question, k=config.TOP_K)
    if not results:
        return 0.0, []
    return results[0].score, [r.chunk.source for r in results]


def main() -> None:
    print("Loading embedding model...\n")
    foundry.get_embedding_client()

    print(f"{'question':<48} {'TR':>6} {'EN':>6} {'gap':>7}  hit")
    print("-" * 84)

    in_scope_tr: List[float] = []
    in_scope_en: List[float] = []
    out_tr: List[float] = []
    out_en: List[float] = []
    tr_hits = en_hits = in_scope = 0

    for turkish, english, expected in PAIRS:
        tr_score, tr_sources = measure(turkish)
        en_score, en_sources = measure(english)
        gap = tr_score - en_score

        if expected:
            in_scope += 1
            in_scope_tr.append(tr_score)
            in_scope_en.append(en_score)
            tr_hit = expected in tr_sources
            en_hit = expected in en_sources
            tr_hits += int(tr_hit)
            en_hits += int(en_hit)
            hit = f"TR={'ok' if tr_hit else 'MISS'} EN={'ok' if en_hit else 'MISS'}"
        else:
            out_tr.append(tr_score)
            out_en.append(en_score)
            hit = "out of scope"

        print(f"{turkish[:46]:<48} {tr_score:6.3f} {en_score:6.3f} {gap:+7.3f}  {hit}")

    print("\n" + "=" * 84)
    print(f"Threshold in use: {config.SIM_THRESHOLD}")
    print()
    print(f"{'':<22} {'TR':>18} {'EN':>18}")
    print(f"{'in-scope lowest':<22} {min(in_scope_tr):18.3f} {min(in_scope_en):18.3f}")
    print(f"{'in-scope mean':<22} {statistics.mean(in_scope_tr):18.3f} "
          f"{statistics.mean(in_scope_en):18.3f}")
    print(f"{'out-of-scope highest':<22} {max(out_tr):18.3f} {max(out_en):18.3f}")
    print(f"{'correct source found':<22} {tr_hits:>15}/{in_scope} "
          f"{en_hits:>15}/{in_scope}")

    below = sum(1 for s in in_scope_tr if s < config.SIM_THRESHOLD)
    print(f"\nTurkish in-scope questions refused by the current threshold: "
          f"{below}/{in_scope}")

    tr_margin = min(in_scope_tr) - max(out_tr)
    en_margin = min(in_scope_en) - max(out_en)
    print(f"Decision margin — TR: {tr_margin:+.3f}   EN: {en_margin:+.3f}")

    if tr_margin > 0:
        suggested = round((min(in_scope_tr) + max(out_tr)) / 2, 2)
        print(f"\nTurkish separates cleanly. A Turkish threshold of about "
              f"{suggested} would sit in the gap.")
    else:
        print("\nTurkish does not separate: in-scope and out-of-scope overlap, "
              "so no single threshold can split them.")

    foundry.unload_all()


if __name__ == "__main__":
    main()
