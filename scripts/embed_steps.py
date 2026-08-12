"""Step-by-step embedding diagnostic with timing.

test_embeddings.py hides which step is slow behind a single call. This runs
the same path one step at a time so a hang is attributable.

Run:  python -m scripts.embed_steps
"""

import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from src import config, foundry  # noqa: E402


def step(label):
    print(f"\n--> {label}", flush=True)
    return time.perf_counter()


def done(started):
    print(f"    ok  ({time.perf_counter() - started:.1f}s)", flush=True)


def main():
    t = step("1. initialize manager")
    manager = foundry.get_manager()
    done(t)

    t = step(f"2. resolve alias {config.EMBEDDING_MODEL_ALIAS}")
    model = manager.catalog.get_model(config.EMBEDDING_MODEL_ALIAS)
    print(f"    id={model.id}  cached={model.is_cached}  loaded={model.is_loaded}", flush=True)
    done(t)

    t = step("3. model.load()   <-- suspect step, may take a while on CPU")
    model.load()
    print(f"    loaded={model.is_loaded}", flush=True)
    done(t)

    t = step("4. get_embedding_client()")
    client = model.get_embedding_client()
    print(f"    model_id={client.model_id}", flush=True)
    done(t)

    t = step("5. generate_embedding() - ONE short string")
    r1 = client.generate_embedding("hello")
    vec = r1.data[0].embedding
    print(f"    dim={len(vec)}  first 3={vec[:3]}", flush=True)
    done(t)

    t = step("6. generate_embeddings() - THREE strings in one call")
    r3 = client.generate_embeddings(["one", "two", "three"])
    print(f"    returned {len(r3.data)} vectors", flush=True)
    done(t)

    t = step("7. unload")
    model.unload()
    done(t)

    print("\nAll steps completed.")


if __name__ == "__main__":
    main()
