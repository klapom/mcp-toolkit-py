"""Follow-up-hints env-flag resolver (Feature 15.2).

Reads ``MCP_FOLLOWUP_HINTS_ENABLED`` from the environment on every call
(no module-level caching) and returns a bool.
"""

from __future__ import annotations

import os

_TRUTHY: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_KILL_SWITCH = "forced_off"


def hints_enabled() -> bool:
    """Return True iff follow-up hints are enabled via the env flag.

    Resolution order:
    1. Strip whitespace, lowercase the raw value.
    2. ``"forced_off"`` → False (kill-switch, wins over everything).
    3. Value in truthy set → True.
    4. Anything else (unset, empty, garbage) → False.
    """
    raw = os.environ.get("MCP_FOLLOWUP_HINTS_ENABLED", "").strip().lower()
    if raw == _KILL_SWITCH:
        return False
    return raw in _TRUTHY
