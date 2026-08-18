"""Single point of contact with the Foundry Local SDK.

Everything else in the project goes through this module. Two reasons:

1. ``FoundryLocalManager`` is a process-wide singleton — calling ``initialize()``
   twice raises. Streamlit reruns the script on every interaction, so the guard
   has to live somewhere central.
2. If Foundry Local has to be swapped out (Ollama, sentence-transformers), only
   this file changes.

Models are downloaded and loaded lazily, then cached for the process lifetime.
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

from foundry_local_sdk import Configuration, FoundryLocalManager
from foundry_local_sdk.logging_helper import LogLevel

from . import config

logger = logging.getLogger(__name__)

# Reentrant on purpose: get_model() holds the lock and then calls
# get_manager(), which needs it too. A plain Lock deadlocks there.
_lock = threading.RLock()
_manager: Optional[FoundryLocalManager] = None
_models: Dict[str, object] = {}
_clients: Dict[str, object] = {}


class ModelNotFoundError(RuntimeError):
    """Raised when a configured alias is not in the local catalog."""


def get_manager() -> FoundryLocalManager:
    """Return the process-wide manager, initializing it on first call."""
    global _manager
    if _manager is not None:
        return _manager

    with _lock:
        if _manager is None:
            # Another import path may already have initialized the singleton.
            if FoundryLocalManager.instance is not None:
                _manager = FoundryLocalManager.instance
            else:
                logger.info("Initializing Foundry Local (app_name=%s)", config.APP_NAME)
                FoundryLocalManager.initialize(
                    Configuration(app_name=config.APP_NAME, log_level=LogLevel.WARNING)
                )
                _manager = FoundryLocalManager.instance
    return _manager


def available_aliases() -> list[str]:
    """Every model alias this machine can run. Useful in error messages."""
    return sorted({m.alias for m in get_manager().catalog.list_models()})


def _progress(percent: float) -> None:
    print(f"\r  downloading... {percent:5.1f}%", end="", flush=True)


_eps_registered = False


def ensure_providers() -> None:
    """Register the execution providers this machine can use.

    Nothing does this by itself, and until it happens the catalogue lists only
    the generic-cpu build of every model — a GPU variant may exist and simply
    be invisible. Registration is quick and idempotent; the packages are
    cached after the first call.
    """
    global _eps_registered
    if _eps_registered or not config.PREFER_GPU:
        return
    _eps_registered = True

    try:
        result = get_manager().download_and_register_eps()
        if result.registered_eps:
            logger.info("Registered execution providers: %s",
                        ", ".join(result.registered_eps))
    except Exception as exc:
        # Not fatal — everything still runs on CPU.
        logger.warning("Could not register execution providers: %s", exc)


def _pick_variant(model):
    """Prefer a GPU build when one exists for this model."""
    if not config.PREFER_GPU:
        return None
    try:
        variants = model.variants
    except Exception:
        return None

    gpu = next((v for v in variants if "gpu" in (v.id or "").lower()), None)
    if gpu is None or gpu.id == model.id:
        return None
    return gpu


def get_model(alias: str, show_progress: bool = True):
    """Download (if needed), load (if needed), and return a model by alias."""
    if alias in _models:
        return _models[alias]

    with _lock:
        if alias in _models:
            return _models[alias]

        manager = get_manager()
        ensure_providers()

        model = manager.catalog.get_model(alias)
        if model is None:
            raise ModelNotFoundError(
                f"Model alias {alias!r} is not in the Foundry Local catalog.\n"
                f"Available aliases: {', '.join(available_aliases())}\n"
                f"Update src/config.py with one of these."
            )

        variant = _pick_variant(model)
        if variant is not None:
            logger.info("Using %s instead of %s", variant.id, model.id)
            model.select_variant(variant)

        if not model.is_cached:
            logger.info("Downloading %s (first run only)", alias)
            if show_progress:
                model.download(progress_callback=_progress)
                print()
            else:
                model.download()

        if not model.is_loaded:
            logger.info("Loading %s into memory", alias)
            model.load()

        _models[alias] = model
        return model


def get_chat_client():
    """OpenAI-compatible chat client for the configured chat model."""
    if "chat" not in _clients:
        model = get_model(config.CHAT_MODEL_ALIAS)
        client = model.get_chat_client()
        client.settings.max_tokens = config.MAX_TOKENS
        client.settings.temperature = config.TEMPERATURE
        client.settings.top_p = config.TOP_P
        client.settings.top_k = config.SAMPLING_TOP_K
        _clients["chat"] = client
    return _clients["chat"]


def get_embedding_client():
    """OpenAI-compatible embedding client for the configured embedding model."""
    if "embedding" not in _clients:
        model = get_model(config.EMBEDDING_MODEL_ALIAS)
        _clients["embedding"] = model.get_embedding_client()
    return _clients["embedding"]


# A real prompt, not "Ready?". Warming up on two words left the first genuine
# question at 12.1s against about 1.5s for the ones after it — the runtime was
# still building whatever it builds for a longer sequence. This filler is
# roughly the length of an answer prompt with an animal's records in it.
_WARM_UP_SYSTEM = (
    "You are Pawprint, a pet health assistant.\n\n"
    "This animal's records:\n"
    "Name: Warmup\nSpecies: cat\nBreed: domestic shorthair\nAge: 3 years\n"
    "Sex: female\nCurrent weight: 4.2 kg (measured 2026-01-01)\n"
    "Target weight: 4.0 kg\nDifference from target: +0.2 kg (+5.0%)\n"
    "Weight change over the last 3 weeks: +0.1 kg\n"
    "Current food: Example Adult Chicken\nDaily amount: 55 g (210 kcal)\n"
    "Calculated daily energy requirement: 205 kcal\n"
    "Amount that would cover it: 54 g of this food\nMeals per day: 2\n"
    "Stool normal in the last 30 days: 90%\n\n"
    "Reference material:\n"
    "Adult cats are usually fed twice a day. Portion sizes on the label are a "
    "starting point and should be adjusted to the individual animal. Weigh the "
    "food rather than measuring it by volume, since density varies between "
    "products. Reassess body condition monthly and weigh weekly during any "
    "change.\n\n"
    "Rules:\n- At most three sentences.\n- Use the animal's actual numbers."
)


def warm_up() -> dict:
    """Load both models and actually run something through them.

    Loading is not enough. On the GPU build the first embedding call failed
    outright with "Operation was cancelled" and the first answer took 64
    seconds, while everything after that took about one. Whatever the runtime
    sets up on first use, it sets up lazily — so the first request pays for it,
    and that request should be ours rather than the user's.

    Failures are swallowed: a warm-up that does not work is not a reason to
    refuse to start.
    """
    import time

    started = time.perf_counter()
    report = {"embedding": None, "chat": None}

    try:
        embedding = get_embedding_client()
        mark = time.perf_counter()
        embedding.generate_embedding("warm up")
        report["embedding"] = round(time.perf_counter() - mark, 1)
    except Exception as exc:
        logger.warning("Embedding warm-up failed: %s", exc)
        try:                      # the first call often fails, the second does not
            get_embedding_client().generate_embedding("warm up")
            report["embedding"] = round(time.perf_counter() - started, 1)
        except Exception as second:
            logger.warning("Embedding warm-up failed again: %s", second)

    try:
        chat = get_chat_client()
        mark = time.perf_counter()
        chat.complete_chat([
            {"role": "system", "content": _WARM_UP_SYSTEM},
            {"role": "user", "content": "Is this amount right?"},
        ])
        report["chat"] = round(time.perf_counter() - mark, 1)
    except Exception as exc:
        logger.warning("Chat warm-up failed: %s", exc)

    report["total"] = round(time.perf_counter() - started, 1)
    logger.info("Warm-up: %s", report)
    return report


def unload_all() -> None:
    """Free model memory. Call on shutdown; safe to call more than once."""
    for alias, model in list(_models.items()):
        try:
            model.unload()
            logger.info("Unloaded %s", alias)
        except Exception as exc:
            logger.warning("Could not unload %s: %s", alias, exc)
    _models.clear()
    _clients.clear()
