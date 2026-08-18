"""What the model says when a question gets past the records gate but the
records cannot answer it.

Written because threshold tuning ran out of road. The gate is meant to separate
questions the records can answer from questions they cannot, and measurement
(scripts/probe_pet_gate.py) shows the two groups overlap in both languages:
pet-domain questions the records do not cover — training, breed choice — score
as high as real ones. No threshold separates them, and moving one only trades
a wrong refusal for a wrong answer.

So the question stops being "where is the threshold" and becomes "what happens
when it is wrong". Two very different things can get through:

  1. "What is the capital of France"  — scores 0.316 EN / 0.192 TR, well below
     every real question. The gate stops these, and this is the class it was
     built for: the model does know the answer and will give it.

  2. "How do I train my puppy to sit" — scores 0.394, above the threshold. Gets
     through. But it reaches SYSTEM_PROMPT_RECORDS_ONLY, which says the model
     knows exactly one thing and must reply with the fallback if the answer is
     not literally in the records.

Whether case 2 matters depends entirely on whether the model honours that
prompt. If it refuses, the leak is harmless and the gate is doing the job it
was built for. If it answers, the gate is the only thing standing between a
user and an invented answer, and it is not enough on its own.

This script forces the records-only path and prints what comes back, so that
question is settled by reading output rather than by argument.

Run:  python -m scripts.probe_records_only
"""

from __future__ import annotations

from src import config, foundry, llm, pet_context, pets_db

# The four that clear the gate but the records cannot answer, plus two that the
# gate stops — included so the contrast is visible in one run.
QUESTIONS = [
    ("en", "how do I train my puppy to sit", "leaks through"),
    ("en", "which dog breed is best for an apartment", "leaks through"),
    ("tr", "köpeğime oturmayı nasıl öğretirim", "leaks through"),
    ("tr", "1998 dünya kupasını kim kazandı", "leaks through"),
    ("en", "what is the capital of France", "gate stops it"),
    ("tr", "fransa'nın başkenti neresi", "gate stops it"),
    # And two the records genuinely answer, to show the path still works.
    ("en", "how old is my cat", "should be answered"),
    ("tr", "kedim kaç aylık", "should be answered"),
]


def main() -> None:
    pet = pets_db.first_pet()
    if pet is None:
        print("No animal on file — add one first.")
        return

    print(f"Pet: {pet.name} ({pet.species})")
    print("Forcing the records-only prompt, gate bypassed.\n")

    foundry.get_chat_client()

    refused = 0
    answered = 0

    for lang, question, note in QUESTIONS:
        prompt = config.system_prompt(lang, records_only=True).format(
            pet_context=pet_context.build(pet, lang),
            fallback=config.fallback(lang),
            language=config.LANGUAGE_INSTRUCTION.get(
                lang, config.LANGUAGE_INSTRUCTION["en"]
            ),
        )
        text = llm.generate(prompt, question).strip()

        # The fallback sentence, allowing for the model padding around it.
        is_refusal = config.fallback(lang).rstrip(".").lower() in text.lower()
        if is_refusal:
            refused += 1
        else:
            answered += 1

        print(f"[{lang}] {question}   ({note})")
        print(f"  {'REFUSED' if is_refusal else 'ANSWERED'}: "
              f"{' '.join(text.split())[:160]}")
        print()

    print("=" * 68)
    print(f"Refused: {refused}   Answered: {answered}")
    print(
        "\nRead it like this. The four 'leaks through' lines are the ones that\n"
        "matter: if they say REFUSED, the strict prompt is catching what the\n"
        "gate lets past, and the overlapping scores are survivable. If they say\n"
        "ANSWERED, the gate is load-bearing and a threshold that cannot be set\n"
        "correctly is a real problem, not a tidiness one."
    )

    foundry.unload_all()


if __name__ == "__main__":
    main()
