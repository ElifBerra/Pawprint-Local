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


def get_model(alias: str, show_progress: bool = True):
    """Download (if needed), load (if needed), and return a model by alias."""
    if alias in _models:
        return _models[alias]

    with _lock:
        if alias in _models:
            return _models[alias]

        manager = get_manager()
        model = manager.catalog.get_model(alias)
        if model is None:
            raise ModelNotFoundError(
                f"Model alias {alias!r} is not in the Foundry Local catalog.\n"
                f"Available aliases: {', '.join(available_aliases())}\n"
                f"Update src/config.py with one of these."
            )

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
        _clients["chat"] = client
    return _clients["chat"]


def get_embedding_client():
    """OpenAI-compatible embedding client for the configured embedding model."""
    if "embedding" not in _clients:
        model = get_model(config.EMBEDDING_MODEL_ALIAS)
        _clients["embedding"] = model.get_embedding_client()
    return _clients["embedding"]


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
