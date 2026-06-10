"""Render helpers for follow-up hints (Sprint 15.5).

Produces the LLM-facing text block and the structured ``_meta`` payload.
Both are deterministic, capped at ``MAX_HINTS``, and never raise on
well-formed input.
"""

from __future__ import annotations

from typing import Any

from mcp_toolkit_py.hints.rules import Hint

MAX_HINTS: int = 3


def format_hints_text(hints: list[Hint]) -> str:
    """Render hints as a German numbered-list text block.

    Returns ``""`` for an empty list. Caps output at ``MAX_HINTS`` entries.
    The ``when`` field is never exposed in the rendered text.
    """
    if not hints:
        return ""

    capped = hints[:MAX_HINTS]
    lines = ["Mögliche nächste Schritte:"]
    for i, hint in enumerate(capped, start=1):
        lines.append(f"{i}. {hint.tool} — {hint.rationale}")
    return "\n".join(lines)


def format_hints_meta(hints: list[Hint]) -> list[dict[str, Any]]:
    """Render hints as a list of plain, JSON-serialisable dicts.

    Returns ``[]`` for an empty list. Caps output at ``MAX_HINTS`` entries.
    The ``when`` field is never included. ``arguments_template`` is included
    only when it is not ``None``.
    """
    if not hints:
        return []

    result: list[dict[str, Any]] = []
    for hint in hints[:MAX_HINTS]:
        d = hint.model_dump(exclude_none=True, exclude={"when"})
        result.append(d)
    return result


def append_hints_to_text(text: str, hints: list[Hint]) -> str:
    """Append a rendered hints block to ``text``.

    - If ``hints`` is empty, ``text`` is returned unchanged.
    - If ``text`` is empty or whitespace-only, only the hints block is
      returned (no leading separator).
    - Otherwise ``text.rstrip()`` + ``"\\n\\n---\\n"`` + hints block.
    """
    if not hints:
        return text

    block = format_hints_text(hints)

    if not text.strip():
        return block

    return text.rstrip() + "\n\n---\n" + block
