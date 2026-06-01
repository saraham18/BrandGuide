"""Thin Anthropic Messages wrapper (lazy import, injectable for tests)."""
from __future__ import annotations

from typing import Any

from .config import Config


def build_client(config: Config) -> Any:
    config.require_llm()
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The 'anthropic' package is required. Install it: pip install anthropic"
        ) from exc
    return anthropic.Anthropic(api_key=config.anthropic_api_key)


def complete(
    config: Config,
    system: str,
    prompt: str,
    *,
    client: Any | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.4,
) -> str:
    client = client or build_client(config)
    message = client.messages.create(
        model=config.model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip()
