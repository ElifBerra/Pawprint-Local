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

What to look for: every 'answerable' score above every 'out of scope' score, in
both languages, with room between them. That gap is what the threshold has to
sit in, and a threshold with no gap around it will be wrong on the day.

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

# Should not. Nothing in the records speaks to these.
OUT_OF_SCOPE = {
    "en": [
        "what is the capital of France",
        "who won the world cup in 1998",
        "how do I train my puppy to sit",
        "which dog breed is best for an apartment",
    ],
    "tr": [
        "fransa'nın başkenti neresi",
        "1998 dünya kupasını kim kazandı",
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

        scores = {"yes": [], "no": []}
        for group, questions in (("yes", ANSWERABLE[lang]),
                                 ("no", OUT_OF_SCOPE[lang])):
            for question in questions:
                vector = retrieve.embed_query(question)
                score = pet_context.relevance(pet, vector, lang)
                scores[group].append(score)

                passes = score >= limit
                # A tick is only good news in the 'yes' group.
                correct = passes if group == "yes" else not passes
                print(f"  {score:6.3f}  {'pass' if passes else 'stop'}  "
                      f"{'  ' if correct else '<<'}  {question}")
            print()

        if scores["yes"] and scores["no"]:
            low, high = min(scores["yes"]), max(scores["no"])
            print(f"  lowest answerable  {low:.3f}")
            print(f"  highest out-of-scope {high:.3f}")
            print(f"  margin {low - high:+.3f}"
                  f"{'' if low > high else '   NO SAFE THRESHOLD EXISTS'}")
            if low > high:
                print(f"  a threshold anywhere in {high:.3f}–{low:.3f} works; "
                      f"the middle is {(low + high) / 2:.2f}")
        print()

    foundry.unload_all()


if __name__ == "__main__":
    main()
