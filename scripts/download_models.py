"""Download the configured models with verbose output.

Separates model download from everything else, so a slow or stalled download
is obvious instead of looking like a hang.

Run:  python -m scripts.download_models
"""

import logging
import time

from src import config, foundry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("foundry_local_sdk").setLevel(logging.INFO)


def fetch(alias: str) -> None:
    print(f"\n{'=' * 60}\n{alias}\n{'=' * 60}")

    manager = foundry.get_manager()
    model = manager.catalog.get_model(alias)

    if model is None:
        print(f"NOT FOUND. Available: {', '.join(foundry.available_aliases())}")
        return

    print(f"id       : {model.id}")
    print(f"cached   : {model.is_cached}")
    print(f"variants : {[v.id for v in model.variants]}")

    if model.is_cached:
        print("Already downloaded, skipping.")
        return

    started = time.time()
    last_report = [0.0]

    def progress(percent: float) -> None:
        # Report every 2% so a stalled download is visible in the log.
        if percent - last_report[0] >= 2.0 or percent >= 100:
            elapsed = time.time() - started
            print(f"  {percent:5.1f}%   {elapsed:6.1f}s elapsed")
            last_report[0] = percent

    print("Downloading...")
    model.download(progress_callback=progress)
    print(f"Done in {time.time() - started:.1f}s")


def main() -> None:
    fetch(config.CHAT_MODEL_ALIAS)
    fetch(config.EMBEDDING_MODEL_ALIAS)
    print("\nAll models ready.")


if __name__ == "__main__":
    main()
