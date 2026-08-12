"""Find out which ChatClientSettings the local runtime actually accepts.

The SDK serialises every setting into the OpenAI-style request, but the ONNX
GenAI backend does not implement all of them, and an unsupported one fails as
"Operation was cancelled" rather than a useful message. This tries each in
isolation.

Run:  python -m scripts.probe_settings
"""

import time

from src import config, foundry

MESSAGES = [
    {"role": "system", "content": "You are a concise assistant."},
    {"role": "user", "content": "Name three colours."},
]

CANDIDATES = [
    ("baseline (max_tokens only)", {"max_tokens": 64}),
    ("temperature", {"max_tokens": 64, "temperature": 0.2}),
    ("top_p", {"max_tokens": 64, "top_p": 0.9}),
    ("top_k", {"max_tokens": 64, "top_k": 40}),
    ("frequency_penalty", {"max_tokens": 64, "frequency_penalty": 0.6}),
    ("presence_penalty", {"max_tokens": 64, "presence_penalty": 0.2}),
    ("random_seed", {"max_tokens": 64, "random_seed": 42}),
]

RESET = {
    "max_tokens": None, "temperature": None, "top_p": None, "top_k": None,
    "frequency_penalty": None, "presence_penalty": None, "random_seed": None,
}


def main():
    print("Loading chat model...")
    model = foundry.get_model(config.CHAT_MODEL_ALIAS)
    client = model.get_chat_client()
    print(f"Model: {client.model_id}\n")

    supported, rejected = [], []

    for label, settings in CANDIDATES:
        for key, value in RESET.items():
            setattr(client.settings, key, value)
        for key, value in settings.items():
            setattr(client.settings, key, value)

        started = time.perf_counter()
        try:
            response = client.complete_chat(MESSAGES)
            text = " ".join((response.choices[0].message.content or "").split())
            print(f"  OK      {label:<28} {time.perf_counter() - started:5.1f}s  {text[:50]}")
            supported.append(label)
        except Exception as exc:
            print(f"  FAILED  {label:<28} {type(exc).__name__}: {str(exc)[:70]}")
            rejected.append(label)

    print(f"\nSupported: {', '.join(supported) or 'none'}")
    print(f"Rejected : {', '.join(rejected) or 'none'}")
    print("\nPut only the supported ones in src/foundry.py.")

    foundry.unload_all()


if __name__ == "__main__":
    main()
