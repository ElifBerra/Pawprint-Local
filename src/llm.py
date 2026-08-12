"""Thin wrapper over the Foundry Local chat client."""

from __future__ import annotations

import logging
from typing import Iterator

from . import foundry

logger = logging.getLogger(__name__)


def generate(system_prompt: str, user_message: str) -> str:
    """One-shot completion. Returns the assistant's text."""
    client = foundry.get_chat_client()
    response = client.complete_chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ])
    content = response.choices[0].message.content
    return (content or "").strip()


def generate_streaming(system_prompt: str, user_message: str) -> Iterator[str]:
    """Yield the answer token by token, for a more responsive UI."""
    client = foundry.get_chat_client()
    stream = client.complete_streaming_chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ])
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
