"""Environment diagnostic for Pawprint-Local.

Run this first whenever something breaks:
    python scripts/check_env.py
"""

import importlib
import sys
import traceback


def section(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main():
    section("PYTHON")
    print("Version   :", sys.version.split()[0])
    print("Executable:", sys.executable)
    in_venv = sys.prefix != sys.base_prefix
    print("In venv   :", in_venv)
    if not in_venv:
        print("  WARNING: venv is not active. Run .\\venv\\Scripts\\Activate.ps1")

    section("PACKAGES")
    for name in ["foundry_local_sdk", "openai", "numpy", "streamlit", "pytest"]:
        try:
            mod = importlib.import_module(name)
            print(f"  OK      {name:<20} {getattr(mod, '__version__', '(no __version__)')}")
        except ImportError as exc:
            print(f"  MISSING {name:<20} ({exc})")

    section("FOUNDRY LOCAL")
    try:
        from foundry_local_sdk import Configuration, FoundryLocalManager
        from foundry_local_sdk.logging_helper import LogLevel

        config = Configuration(app_name="pawprint-local", log_level=LogLevel.WARNING)
        FoundryLocalManager.initialize(config)
        manager = FoundryLocalManager.instance
        print("Manager initialized OK")
    except Exception:
        print("FAILED to initialize FoundryLocalManager:\n")
        traceback.print_exc()
        print("\nTry in PowerShell:  foundry server restart")
        return

    # Execution providers must be registered before models can run.
    try:
        eps = manager.discover_eps()
        print(f"\nExecution providers ({len(eps)}):")
        for ep in eps:
            print(f"  {ep}")
    except Exception as exc:
        print(f"\ndiscover_eps failed: {type(exc).__name__}: {exc}")

    # Full catalog. Copy the aliases you need into src/config.py.
    try:
        models = manager.catalog.list_models()
        print(f"\nCatalog models ({len(models)}):")
        seen = set()
        for m in models:
            if m.alias in seen:
                continue
            seen.add(m.alias)
            caps = m.capabilities or "-"
            cached = "cached" if m.is_cached else ""
            print(f"  {m.alias:<38} {caps:<24} {cached}")
    except Exception:
        print("\nlist_models failed:\n")
        traceback.print_exc()

    print("\nCached models:")
    try:
        for m in manager.catalog.get_cached_models():
            print(f"  {m.alias:<38} {m.id}")
    except Exception as exc:
        print(f"  failed: {exc}")


if __name__ == "__main__":
    main()
