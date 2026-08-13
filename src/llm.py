"""Thin wrapper over the Foundry Local chat client."""

from __future__ import annotations

import logging
import re
from typing import Dict, Iterator, List

from . import config, foundry

logger = logging.getLogger(__name__)

# Qwen3 models reason out loud by default, emitting a <think> block before the
# answer. On CPU that is time spent on text the user never sees, and the block
# came out in English even when the answer was asked for in Turkish. Qwen
# exposes a soft switch: "/no_think" in the prompt disables it for that turn.
_THINKING_MODELS = ("qwen3",)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _wants_no_think() -> bool:
    alias = (config.CHAT_MODEL_ALIAS or "").lower()
    return any(alias.startswith(prefix) for prefix in _THINKING_MODELS)


def _messages(system_prompt: str, user_message: str) -> List[Dict[str, str]]:
    if _wants_no_think():
        # Qwen documents the switch in either turn; the runtime here honours
        # neither reliably, so it goes in both.
        system_prompt = f"/no_think\n\n{system_prompt}"
        user_message = f"{user_message} /no_think"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]


def _clean(text: str) -> str:
    """Drop any reasoning block that survived the switch.

    An unterminated block means the token budget ran out mid-thought and there
    is no answer to salvage — returning the raw reasoning would be worse than
    returning nothing, since it reads like an answer but is the model talking
    to itself.
    """
    cleaned = _THINK_BLOCK.sub("", text).strip()
    if cleaned.startswith("<think>"):
        return ""
    return cleaned


def generate(system_prompt: str, user_message: str) -> str:
    """One-shot completion. Returns the assistant's text."""
    client = foundry.get_chat_client()
    response = client.complete_chat(_messages(system_prompt, user_message))
    content = response.choices[0].message.content or ""
    return _clean(content)


def generate_streaming(system_prompt: str, user_message: str) -> Iterator[str]:
    """Yield the answer as it arrives.

    Reasoning blocks are suppressed rather than filtered, because a filter
    cannot work on a stream that has not finished. If one appears anyway, its
    opening tag is detected and the block is held back until it closes.
    """
    client = foundry.get_chat_client()
    stream = client.complete_streaming_chat(_messages(system_prompt, user_message))

    buffer = ""
    inside_thinking = False

    for chunk in stream:
        if not chunk.choices or not chunk.choices[0].delta.content:
            continue
        buffer += chunk.choices[0].delta.content

        while buffer:
            if inside_thinking:
                end = buffer.find("</think>")
                if end == -1:
                    buffer = ""
                    break
                buffer = buffer[end + len("</think>"):]
                inside_thinking = False
                continue

            start = buffer.find("<think>")
            if start == -1:
                # Hold back a possible partial "<think>" split across chunks.
                safe = len(buffer) - len("<think>") + 1
                if safe > 0 and "<" in buffer[safe:]:
                    emit, buffer = buffer[:safe], buffer[safe:]
                else:
                    emit, buffer = buffer, ""
                if emit:
                    yield emit
                break

            if start > 0:
                yield buffer[:start]
            buffer = buffer[start + len("<think>"):]
            inside_thinking = True

    if buffer and not inside_thinking:
        yield buffer
