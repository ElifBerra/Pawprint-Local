"""Score a handful of questions against the collection, with and without the
animal's context folded in.

People leave out what is obvious to them. "Can I give chocolate?" is a question
about their own cat, but the word "cat" never appears, and the collection is
matched on what was written rather than what was meant. This shows the size of
that gap.

Run:  python -m scripts.probe_query
      python -m scripts.probe_query "is this urgent" "how much food"
"""

from __future__ import annotations

import sys

from src import config, foundry, pet_context, pets_db, retrieve

DEFAULT_QUERIES = [
    "can i give chocolate",
    "Can I give my dog chocolate?",
    "is chocolate bad for cats",
    "chocolate",
    "how often should i feed",
    "is this urgent",
    "when are the shots due",
    "how much does neutering cost",     # in domain, not in the documents
    "who won the world cup in 1998",    # out of domain
]


def main() -> None:
    queries = sys.argv[1:] or DEFAULT_QUERIES

    pet = pets_db.first_pet()
    terms = pet_context.search_terms(pet)
    limit = config.threshold("en")

    print(f"Pet    : {pet.name if pet else '—'}")
    print(f"Terms  : {terms or '—'}")
    print(f"Limit  : {limit}\n")

    foundry.get_embedding_client()

    print(f"{'plain':>7}  {'+context':>9}  {'gain':>6}  question")
    print("-" * 72)

    for query in queries:
        plain = retrieve.get_top_chunks(query)
        with_terms = retrieve.get_top_chunks(query, context_terms=terms)

        a = plain[0].score if plain else 0.0
        b = with_terms[0].score if with_terms else 0.0

        mark = lambda s: "ok " if s >= limit else "   "
        print(f"{a:7.3f}{mark(a)}{b:8.3f}{mark(b)}{b - a:+7.3f}  {query}")

    print("\n'ok' means the question clears the threshold and reaches the model.")
    foundry.unload_all()


if __name__ == "__main__":
    main()
