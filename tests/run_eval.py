"""Full evaluation over tests/eval_questions.json.

Separate from scripts/bench.py: bench is a fast 8-question latency check during
tuning, this is the graded run that goes into the report.

Two things are measured independently, because they fail for different reasons:

  Retrieval  - did the right document reach the prompt at all?
  Behaviour  - did the assistant answer when it should, and decline when it
               should not?

A question can retrieve correctly and still be answered badly, so separating
them tells you which layer to fix.

Run:  python -m tests.run_eval
      python -m tests.run_eval --save docs/eval-results.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import List

from src import config, db, foundry, rag

QUESTIONS_PATH = Path(__file__).parent / "eval_questions.json"


def load_questions() -> List[dict]:
    with QUESTIONS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def evaluate(case: dict) -> dict:
    result = rag.answer(case["question"])
    retrieved_sources = [r.chunk.source for r in result.retrieved]
    top_score = result.retrieved[0].score if result.retrieved else 0.0

    answerable = case["answerable"]
    expected = case.get("expected_source")

    if answerable:
        retrieval_ok = expected in retrieved_sources
        behaviour_ok = not result.used_fallback
    else:
        retrieval_ok = None          # nothing to retrieve, not scored
        behaviour_ok = result.used_fallback

    return {
        "question": case["question"],
        "answerable": answerable,
        "expected": expected,
        "retrieved": retrieved_sources,
        "top_score": top_score,
        "retrieval_ok": retrieval_ok,
        "behaviour_ok": behaviour_ok,
        "latency": result.latency_s,
        "answer": " ".join(result.text.split()),
        "note": case.get("note", ""),
    }


def report(rows: List[dict]) -> List[str]:
    out: List[str] = []
    add = out.append

    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]

    retrieval_hits = sum(1 for r in answerable if r["retrieval_ok"])
    answered_ok = sum(1 for r in answerable if r["behaviour_ok"])
    declined_ok = sum(1 for r in unanswerable if r["behaviour_ok"])

    latencies = [r["latency"] for r in rows]
    ans_scores = [r["top_score"] for r in answerable]
    un_scores = [r["top_score"] for r in unanswerable]

    add("# Değerlendirme Sonuçları")
    add("")
    add(f"Tarih: {time.strftime('%Y-%m-%d %H:%M')}")
    add("")
    add(f"Ayarlar: `chunk_size={config.CHUNK_SIZE} overlap={config.CHUNK_OVERLAP} "
        f"top_k={config.TOP_K} max_tokens={config.MAX_TOKENS} "
        f"threshold={config.SIM_THRESHOLD}`")
    stats = db.stats()
    add(f"Külliyat: {stats['chunks']} chunk / {stats['sources']} kaynak")
    add(f"Model: `{config.CHAT_MODEL_ALIAS}` + `{config.EMBEDDING_MODEL_ALIAS}`")
    add("")
    add("## Özet")
    add("")
    add("| Metrik | Sonuç |")
    add("|---|---|")
    add(f"| Retrieval isabeti (doğru kaynak top-{config.TOP_K}'te) | "
        f"{retrieval_hits}/{len(answerable)} |")
    add(f"| Cevaplanması gerekeni cevapladı | {answered_ok}/{len(answerable)} |")
    add(f"| Reddetmesi gerekeni reddetti | {declined_ok}/{len(unanswerable)} |")
    add(f"| Ortalama gecikme | {statistics.mean(latencies):.1f}s |")
    add(f"| Medyan gecikme | {statistics.median(latencies):.1f}s |")
    add("")
    add("## Benzerlik skorları")
    add("")
    add("| Grup | En düşük | En yüksek | Ortalama |")
    add("|---|---|---|---|")
    if ans_scores:
        add(f"| Cevaplanabilir | {min(ans_scores):.3f} | {max(ans_scores):.3f} | "
            f"{statistics.mean(ans_scores):.3f} |")
    if un_scores:
        add(f"| Cevaplanamaz | {min(un_scores):.3f} | {max(un_scores):.3f} | "
            f"{statistics.mean(un_scores):.3f} |")
    add("")
    if ans_scores and un_scores:
        margin = min(ans_scores) - max(un_scores)
        add(f"Karar payı: en düşük cevaplanabilir skor ile en yüksek cevaplanamaz "
            f"skor arasında **{margin:+.3f}**. Eşik {config.SIM_THRESHOLD}.")
        if margin <= 0:
            add("")
            add("> Pay negatif: iki grup üst üste biniyor, tek bir eşik ikisini "
                "ayıramaz.")
    add("")

    failures = [r for r in rows if r["behaviour_ok"] is False
                or r["retrieval_ok"] is False]
    add(f"## Başarısızlıklar ({len(failures)})")
    add("")
    if not failures:
        add("Yok.")
    for row in failures:
        add(f"**{row['question']}**")
        add("")
        add(f"- beklenen kaynak: `{row['expected'] or '-'}`")
        add(f"- çekilen: {', '.join(f'`{s}`' for s in row['retrieved']) or '-'}")
        add(f"- en yüksek skor: {row['top_score']:.3f}")
        add(f"- retrieval: {row['retrieval_ok']}  davranış: {row['behaviour_ok']}")
        if row["note"]:
            add(f"- not: {row['note']}")
        add(f"- cevap: {row['answer'][:200]}")
        add("")

    add("## Tüm sorular")
    add("")
    add("| # | Soru | Skor | Retrieval | Davranış | Süre |")
    add("|---|---|---|---|---|---|")
    for i, row in enumerate(rows, 1):
        mark = lambda v: "-" if v is None else ("ok" if v else "**FAIL**")
        add(f"| {i} | {row['question']} | {row['top_score']:.3f} | "
            f"{mark(row['retrieval_ok'])} | {mark(row['behaviour_ok'])} | "
            f"{row['latency']:.1f}s |")

    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", metavar="PATH", help="write the report to a file")
    args = parser.parse_args()

    if not config.DB_PATH.exists() or db.count() == 0:
        print("No chunks in the database. Run: python -m src.ingest")
        sys.exit(1)

    cases = load_questions()
    print(f"Evaluating {len(cases)} questions...\n")

    foundry.get_chat_client()
    foundry.get_embedding_client()

    rows = []
    for i, case in enumerate(cases, 1):
        row = evaluate(case)
        rows.append(row)
        flag = "ok  " if (row["behaviour_ok"] and row["retrieval_ok"] is not False) else "FAIL"
        print(f"  [{i:>2}/{len(cases)}] {flag} {row['latency']:5.1f}s  {row['question'][:60]}")

    print()
    lines = report(rows)
    print("\n".join(lines))

    if args.save:
        path = Path(args.save)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nSaved to {path}")

    foundry.unload_all()


if __name__ == "__main__":
    main()
