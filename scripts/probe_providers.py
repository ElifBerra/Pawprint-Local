"""Find out whether a faster execution provider is available on this machine.

Foundry Local only offers model variants built for execution providers that are
registered. We never called download_and_register_eps(), so the catalogue has
only ever shown the generic-cpu build — a GPU variant of the same model may
exist and simply be invisible.

This reports the situation first and only downloads when asked, because
provider packages are large.

Run:  python -m scripts.probe_providers            # report only
      python -m scripts.probe_providers --register # download and register
      python -m scripts.probe_providers --register --only WebGpuExecutionProvider
"""

from __future__ import annotations

import argparse
import time

from src import config, foundry


def show_variants(manager, alias: str, label: str) -> None:
    model = manager.catalog.get_model(alias)
    if model is None:
        print(f"{label}: alias {alias!r} not in the catalogue")
        return
    print(f"{label} — variants of {alias}:")
    for variant in model.variants:
        cached = " (cached)" if variant.is_cached else ""
        print(f"    {variant.id}{cached}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--register", action="store_true",
                        help="download and register the providers")
    parser.add_argument("--only", action="append",
                        help="restrict to named providers, may be repeated")
    parser.add_argument("--alias", default=config.CHAT_MODEL_ALIAS)
    args = parser.parse_args()

    manager = foundry.get_manager()

    print("Execution providers")
    print("-" * 60)
    try:
        providers = manager.discover_eps()
    except Exception as exc:
        print(f"discover_eps failed: {type(exc).__name__}: {exc}")
        return

    for provider in providers:
        state = "registered" if provider.is_registered else "not registered"
        print(f"  {provider.name:<32} {state}")

    print()
    show_variants(manager, args.alias, "Before")

    if not args.register:
        print("\nReport only. Re-run with --register to download and register.")
        print("A GPU variant appearing afterwards is what would make this "
              "worth doing.")
        foundry.unload_all()
        return

    names = args.only or None
    print(f"\nRegistering {names or 'all discoverable providers'}...")
    print("Provider packages are large; this can take several minutes.\n")

    last = [0.0]

    def progress(name: str, percent: float) -> None:
        if percent - last[0] >= 5 or percent >= 100:
            print(f"  {name:<32} {percent:5.1f}%")
            last[0] = percent

    started = time.perf_counter()
    try:
        result = manager.download_and_register_eps(
            names=names, progress_callback=progress
        )
    except Exception as exc:
        print(f"\nFailed: {type(exc).__name__}: {exc}")
        foundry.unload_all()
        return

    print(f"\nDone in {time.perf_counter() - started:.0f}s")
    print(f"  status     : {result.status}")
    print(f"  registered : {result.registered_eps or '—'}")
    print(f"  failed     : {result.failed_eps or '—'}")

    print()
    show_variants(manager, args.alias, "After")

    print("\nIf a variant other than generic-cpu appeared, set it as the model "
          "and re-run the benchmark:")
    print("    python -m scripts.bench --stream")

    foundry.unload_all()


if __name__ == "__main__":
    main()
