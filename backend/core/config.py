"""Centralized application settings for the HTTP interface.

pydantic-settings, backed by the repo-root ``.env`` (the same file the MCP
server and the agents read). This is the typed view of configuration; the
older modules under ``src/`` still read ``os.environ`` directly at import
time, so :meth:`Settings.apply_to_environ` pushes these values back out
before those modules are imported (see ``backend/app/_bootstrap.py``).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- FRED -------------------------------------------------------------
    # Leave FRED_API_KEY unset to run against the built-in synthetic fixture
    # (fred_client falls back to offline automatically). FRED_OFFLINE forces
    # it either way: "1"/"0", or "" for the automatic behaviour.
    fred_api_key: str = ""
    fred_offline: str = ""

    # --- Cost guardrail -------------------------------------------------
    # Rough per-session token budget enforced by cost_tracker.guard_or_shrink
    # on every /observations and /compare call — identical to the MCP path.
    session_token_budget: int = 50000

    # --- API ----------------------------------------------------------
    api_title: str = "Econ Data API"
    api_version: str = "0.1.0"
    # Comma-separated; a plain string (not list[str]) so it can be passed as a
    # single --set-env-vars value without JSON-quoting. Defaults to the Vite
    # dev server.
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    def apply_to_environ(self) -> None:
        """Materialize settings into ``os.environ`` for the ``src/`` modules
        that read it directly (``fred_client``, ``cost_tracker``, ...).

        Precedence stays intuitive: a value already in the real environment
        wins over ``.env`` wins over a default here — we only fill blanks.
        """
        for name, value in {
            "FRED_API_KEY": self.fred_api_key,
            "FRED_OFFLINE": self.fred_offline,
            "SESSION_TOKEN_BUDGET": str(self.session_token_budget),
        }.items():
            if value != "" and name not in os.environ:
                os.environ[name] = value


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance."""
    return Settings()
