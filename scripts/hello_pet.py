"""Pawprint-Local — Foundry Local smoke test.

Verifies that the SDK initializes, a chat model downloads and loads, and that
we can get a completion back. Run this before building anything else.

Run:  python scripts/hello_pet.py
"""

import sys

from foundry_local_sdk import Configuration, FoundryLocalManager
from foundry_local_sdk.logging_helper import LogLevel

# Alias from the Foundry Local catalog. Run scripts/check_env.py to see the
# full list of aliases available on this machine.
ALIAS = "phi-3.5-mini"


def on_progress(percent: float) -> None:
    print(f"\r  downloading... {percent:5.1f}%", end="", flush=True)


def main():
    config = Configuration(app_name="pawprint-local", log_level=LogLevel.WARNING)
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    model = manager.catalog.get_model(ALIAS)
    if model is None:
        print(f"Model alias '{ALIAS}' not found in the catalog.")
        print("Run 'python scripts/check_env.py' and pick an alias from the list.")
        sys.exit(1)

    print(f"Model: {model.alias}  ({model.id})")
    print(f"Cached: {model.is_cached}  Context length: {model.context_length}")

    if not model.is_cached:
        print("Downloading (first run only, this takes a few minutes)...")
        model.download(progress_callback=on_progress)
        print()

    print("Loading into memory...")
    model.load()

    chat = model.get_chat_client()
    chat.settings.max_tokens = 200
    chat.settings.temperature = 0.2

    response = chat.complete_chat([
        {"role": "system", "content": "You are a helpful pet health assistant."},
        {"role": "user", "content": "Hello! What is RAG in one sentence?"},
    ])

    print("\nPawprint Local - Hello Pet Test")
    print("-" * 50)
    print(response.choices[0].message.content)
    print("-" * 50)

    model.unload()
    print("Model unloaded. Setup is working.")


if __name__ == "__main__":
    main()
