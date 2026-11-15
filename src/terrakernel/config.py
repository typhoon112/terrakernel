"""Runtime configuration for TerraKernel.

Everything is read from environment variables so the same code runs in the CLI,
in tests and in the site exporter. Credentials are never read here: the
Anthropic SDK resolves them itself from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"

# Short aliases used on the command line and in evaluation reports.
MODEL_ALIASES = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}

# Public list prices in USD per million tokens (input, output, cache read, cache write).
# Used only for cost *estimates* in reports; the gateway may bill differently.
MODEL_PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}

LLM_MODES = ("live", "record", "replay", "auto")


def resolve_model(name: str | None) -> str:
    if not name:
        return os.environ.get("TK_MODEL", DEFAULT_MODEL)
    return MODEL_ALIASES.get(name, name)


@dataclass
class Settings:
    """Process-wide settings, built once from the environment."""

    model: str = field(default_factory=lambda: resolve_model(None))
    # live: always call the API; record: call and store responses;
    # replay: only serve stored responses (offline, fails on a miss);
    # auto: serve stored responses when present, otherwise call and store.
    llm_mode: str = field(default_factory=lambda: os.environ.get("TK_LLM_MODE", "auto"))
    llm_cache_dir: Path | None = field(
        default_factory=lambda: Path(os.environ["TK_LLM_CACHE"]) if os.environ.get("TK_LLM_CACHE") else None
    )
    max_concurrency: int = field(default_factory=lambda: int(os.environ.get("TK_CONCURRENCY", "3")))
    request_timeout_s: float = field(default_factory=lambda: float(os.environ.get("TK_TIMEOUT", "600")))
    # Structured-output strategy override; empty means "probe and pick".
    structured_strategy: str = field(default_factory=lambda: os.environ.get("TK_STRUCTURED", ""))

    def __post_init__(self) -> None:
        if self.llm_mode not in LLM_MODES:
            raise ValueError(f"TK_LLM_MODE must be one of {LLM_MODES}, got {self.llm_mode!r}")


def get_settings() -> Settings:
    return Settings()
