"""Find which part of the personalised prompt the runtime rejects.

`Operation was cancelled` carries no detail, so the prompt is built up in
stages: plain English, then Turkish input, then the Turkish instruction, then
the full pet-aware prompt. The first failure names the cause.

Run:  python -m scripts.probe_prompt
"""

from __future__ import annotations

import time

from src import config, foundry, pet_context, pets_db, rag

SHORT_SYSTEM = "You are a concise assistant. Answer in one sentence."


def attempt(label: str, system: str, user: str) -> bool:
    client = foundry.get_chat_client()
    total = len(system) + len(user)
    ascii_only = (system + user).isascii()
    started = time.perf_counter()
    try:
        response = client.complete_chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        text = " ".join((response.choices[0].message.content or "").split())
        print(f"  OK      {label:<34} {total:>5} chars  ascii={ascii_only}  "
              f"{time.perf_counter() - started:5.1f}s")
        print(f"          {text[:110]}")
        return True
    except Exception as exc:
        print(f"  FAILED  {label:<34} {total:>5} chars  ascii={ascii_only}")
        print(f"          {type(exc).__name__}: {str(exc)[:110]}")
        return False


def main() -> None:
    pet = pets_db.first_pet()
    if pet is None:
        print("No pet found. Run: python -m scripts.seed_demo --reset")
        return

    print(f"Pet: {pet.name}\nLoading chat model...\n")
    foundry.get_chat_client()

    tr_question = "Bella kilo alıyor. 2,5 bardak Acme Premium yiyor. Normal mi?"
    en_question = "Bella is gaining weight on 2.5 cups of Acme Premium. Is that normal?"

    print("Stage 1 — isolate the input")
    attempt("english system + english user", SHORT_SYSTEM, en_question)
    attempt("english system + TURKISH user", SHORT_SYSTEM, tr_question)
    attempt("TURKISH system + turkish user",
            "Kısa ve net cevap ver. Tek cümle yeter.", tr_question)

    print("\nStage 2 — isolate the prompt size")
    records = pet_context.build(pet, "en")
    print(f"  (pet context is {len(records)} chars)")
    attempt("short system + records", SHORT_SYSTEM + "\n\n" + records, en_question)

    print("\nStage 3 — the real prompts")
    for lang, question in (("en", en_question), ("tr", tr_question)):
        _, prompt, _ = rag._prepare(question, None, None, None, pet, lang)
        if prompt is None:
            print(f"  SKIPPED full prompt ({lang}): below threshold, no model call")
            continue
        attempt(f"full pet prompt, lang={lang}", prompt, question)

    foundry.unload_all()


if __name__ == "__main__":
    main()
