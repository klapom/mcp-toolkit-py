"""Base pydantic-settings class for MCP services.

Process-env wins over ``.env`` (ADR-010). Subclass per service to add
upstream/backend fields while inheriting port + log_level defaults.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    listen_port: int = 32000
    mcp_port: int = 33000
    log_level: Literal["debug", "info", "warning", "error"] = "info"
