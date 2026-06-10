"""Pydantic v2 models for follow-up-hints rule sets (Sprint 15.1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Hint(BaseModel):
    """A single follow-up hint entry."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    rationale: str
    when: str | None = None
    arguments_template: dict[str, str] | None = None


class ToolHints(BaseModel):
    """Per-source-tool container holding a list of hints."""

    model_config = ConfigDict(extra="forbid")

    hints: list[Hint] = Field(default_factory=list)


class HintsRuleSet(BaseModel):
    """Top-level hints rule set document."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    tools: dict[str, ToolHints] = Field(default_factory=dict)
