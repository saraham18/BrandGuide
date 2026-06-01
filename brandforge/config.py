"""Configuration: bring-your-own Claude key via env / a local .env file."""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-4-6"


def load_dotenv(path: str | os.PathLike = ".env") -> dict:
    """Minimal .env loader (no third-party dependency)."""
    parsed: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return parsed
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        parsed[key] = value
        os.environ.setdefault(key, value)
    return parsed


class MissingCredential(RuntimeError):
    """Raised when an operation needs a credential that isn't configured."""


class Config:
    def __init__(self, env: dict | None = None):
        env = env if env is not None else os.environ
        self.anthropic_api_key = env.get("ANTHROPIC_API_KEY")
        self.model = env.get("BRANDFORGE_MODEL", DEFAULT_MODEL)

    def require_llm(self) -> None:
        if not self.anthropic_api_key:
            raise MissingCredential(
                "ANTHROPIC_API_KEY is not set. Add it to your environment or "
                ".env file (see .env.example)."
            )

    @classmethod
    def load(cls, dotenv_path: str | os.PathLike = ".env") -> "Config":
        load_dotenv(dotenv_path)
        return cls()
