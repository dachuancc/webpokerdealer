"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("WPD_HOST", "0.0.0.0")
    port: int = _int_env("WPD_PORT", 8000)
    max_seats: int = _int_env("WPD_MAX_SEATS", 9)
    # Empty string means "trust the request host" (usual for LAN use).
    public_base_url: str = os.getenv("WPD_PUBLIC_BASE_URL", "")


settings = Settings()
