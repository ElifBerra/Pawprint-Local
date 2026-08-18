"""Score questions against the animal's records — the second gate.

The first gate asks whether the documents cover a question. This one asks
whether the *records* do, and it is the gate that decides questions like "how
old is my cat", which no document can answer and which the model must not
answer from memory.

Written after a demo recording caught the gate failing in Turkish:

    selam, kedim kaç aylık   ->  refused
    how old is my cat        ->  "10 months old"

Same records, same information, two languages, two answers. The topics text
being compared against was English, so a Turkish question paid a cross-language
penalty for no reason — the records are not a document, they are a list this
project writes itself, and it can write it in Turkish too.

Not every question the records cannot answer is the same kind of problem, and
the first version of this script failed by treating them alike — it reported
"no safe threshold exists" for a gate that was working, because it counted a
harmless pass as a failure. Three groups now:

  answerable   the records hold the answer. Must pass.
  model knows  capital cities, football results. The model answers these from
               memory whatever the prompt says, so the threshold is the only
               defence and needs clear room above them.
  domain gap   about animals, not in the records. May pass: the records-only
               prompt refuses them, measured in scripts/probe_records_only.py.

What to look for: every answerable score above every 'model knows' score, with
room between. The domain-gap lines are information, not failures.

Run:  python -m scripts.probe_pet_gate
"""

from __future__ import annotations

from src import config, foundry, pet_context, pets_db, retrieve

# Should reach the records.
ANSWERABLE = {
    "en": [
        "how old is my cat",
        "how much does she weigh",
        "what is she eating",
        "is she at a healthy weight",
        "when is her next vaccination",
        "how many meals a day does she get",
    ],
    "tr": [
        "kedim kaç aylık",
        "selam, kedim kaç aylık",
        "kaç kilo",
        "ne yiyor",
        "kilosu ideal mi",
        "bir sonraki aşısı ne zaman",
        "günde kaç öğün yiyor",
    ],
}

# The gate has to stop these. The model knows the answers and gives them: put
# past the gate, it replied "Paris fransa'nın başkentinerdir" from a prompt
# that says it knows only this cat's records. Nothing in the wording holds, so
# the threshold is the whole defence and needs room above these scores.
MODEL_KNOWS = {
    "en": [
        "what is the capital of France",
        "who won the world cup in 1998",
    ],
    "tr": [
        "fransa'nın başkenti neresi",
        "1998 dünya kupasını kim kazandı",
    ],
}

# These may pass. They are about animals but the records hold no answer, and
# the records-only prompt refuses them — measured, in both languages, in
# scripts/probe_records_only.py. They score as high as real questions because
# they are the same kind of text, and no threshold separates them. Treating
# that as a failure would mean refusing real questions to prevent a refusal.
DOMAIN_GAP = {
    "en": [
        "how do I train my puppy to sit",
        "which dog breed is best for an apartment",
    ],
    "tr": [
        "köpeğime oturmayı nasıl öğretirim",
        "apartman için en iyi köpek cinsi hangisi",
    ],
}


def main() -> None:
    pet = pets_db.first_pet()
    if pet is None:
        print("No animal on file — add one first.")
        return

    print(f"Pet: {pet.name} ({pet.species})\n")
    foundry.get_embedding_client()

    for lang in config.LANGUAGES:
        limit = config.pet_threshold(lang)
        print(f"=== {lang.upper()}   threshold {limit}")
        print(f"topics: {pet_context.topics_text(pet, lang)[:90]}...\n")

        groups = (
            ("answerable — must pass", ANSWERABLE[lang], True),
            ("model knows — must stop", MODEL_KNOWS[lang], False),
            ("domain gap — may pass, prompt refuses", DOMAIN_GAP[lang], None),
        )

        scores = {}
        for name, questions, must_pass in groups:
            print(f"  {name}")
            collected = []
            for question in questions:
                vector = retrieve.embed_query(question)
                score = pet_context.relevance(pet, vector, lang)
                collected.append(score)

                passes = score >= limit
                # None means either outcome is acceptable.
                wrong = must_pass is not None and passes != must_pass
                print(f"    {score:6.3f}  {'pass' if passes else 'stop'}  "
                      f"{'<<' if wrong else '  '}  {question}")
            scores[name] = collected
            print()

        low = min(scores["answerable — must pass"])
        high = max(scores["model knows — must stop"])
        print(f"  lowest real question     {low:.3f}")
        print(f"  highest the model knows  {high:.3f}")
        if low > high:
            print(f"  margin {low - high:+.3f} — "
                  f"any threshold in {high:.3f}–{low:.3f} works, "
                  f"middle {(low + high) / 2:.2f}, currently {limit}")
        else:
            print(f"  margin {low - high:+.3f}   NO SAFE THRESHOLD EXISTS")
        print()

    foundry.unload_all()


if __name__ == "__main__":
    main()
