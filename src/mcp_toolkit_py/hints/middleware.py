"""FollowupHintsMiddleware — orchestrates rules, flag, and matcher (Sprint 15.4).

Construction modes
------------------
``FollowupHintsMiddleware(rules=<HintsRuleSet>)``
    Use a pre-loaded rule set.

``FollowupHintsMiddleware(rules_path=<Path|str>, known_tools=<set[str]>)``
    Load rules from YAML and validate against known tools.

Exactly one of ``rules`` / ``rules_path`` must be supplied; mixing both or
omitting both raises ValueError.  ``rules_path`` without ``known_tools``
also raises ValueError.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_toolkit_py.hints import matcher
from mcp_toolkit_py.hints.flag import hints_enabled
from mcp_toolkit_py.hints.loader import load_rules_for_known_tools
from mcp_toolkit_py.hints.rules import Hint, HintsRuleSet

_SENTINEL = object()


class FollowupHintsMiddleware:
    """Orchestrate hint selection for a single tool invocation."""

    def __init__(
        self,
        *,
        rules: HintsRuleSet | object = _SENTINEL,
        rules_path: Path | str | object = _SENTINEL,
        known_tools: set[str] | object = _SENTINEL,
    ) -> None:
        rules_given = rules is not _SENTINEL
        path_given = rules_path is not _SENTINEL

        if rules_given and path_given:
            raise ValueError("Provide either 'rules' or 'rules_path', not both.")
        if not rules_given and not path_given:
            raise ValueError(
                "Provide either 'rules=<HintsRuleSet>' or 'rules_path=<path> + known_tools=<set>'."
            )
        if path_given and known_tools is _SENTINEL:
            raise ValueError("'rules_path' requires 'known_tools' to be provided as well.")

        if rules_given:
            self._rule_set: HintsRuleSet = rules  # type: ignore[assignment]
        else:
            self._rule_set = load_rules_for_known_tools(
                rules_path,  # type: ignore[arg-type]
                known_tools,  # type: ignore[arg-type]
            )

    def select_hints(
        self,
        tool_name: str,
        request_arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> list[Hint]:
        """Return the list of hints that apply for this tool invocation.

        Evaluation order:
        1. Check ``hints_enabled()`` — return [] immediately if False.
        2. Look up ``tool_name`` in the rule set — return [] if absent.
        3. For each hint:
           - No ``when`` clause → always include.
           - ``when`` clause → evaluate via ``matcher.evaluate``; skip on
             ValueError (malformed expression must not crash a tool call).
        """
        # Step 1: env-flag gate (first, before ANY rule or matcher access)
        if not hints_enabled():
            return []

        # Step 2: tool lookup
        tool_hints = self._rule_set.tools.get(tool_name)
        if tool_hints is None:
            return []

        # Build context (do not mutate the caller's dicts)
        ctx: dict[str, Any] = {
            "result": result,
            "request": {"arguments": request_arguments},
        }

        # Step 3: per-hint evaluation
        selected: list[Hint] = []
        for hint in tool_hints.hints:
            if hint.when is None:
                selected.append(hint)
            else:
                try:
                    if matcher.evaluate(hint.when, ctx):
                        selected.append(hint)
                except ValueError:
                    # Malformed/forbidden expression — skip silently
                    pass

        return selected
