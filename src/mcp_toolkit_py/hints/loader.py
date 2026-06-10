"""YAML loader for follow-up-hints rule sets (Sprint 15.1)."""

from __future__ import annotations

from pathlib import Path

import yaml

from mcp_toolkit_py.hints.rules import HintsRuleSet


def load_rules(path: Path | str) -> HintsRuleSet:
    """Load a HintsRuleSet from a YAML file at *path*.

    Raises:
        FileNotFoundError: if *path* does not exist.
        yaml.YAMLError: if the file is not valid YAML.
        ValidationError: if the parsed document does not match the schema.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Hints rules file not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text)  # raises yaml.YAMLError on parse failure

    return HintsRuleSet.model_validate(data)  # raises ValidationError on schema fail


def load_rules_for_known_tools(
    path: Path | str,
    known_tools: set[str],
) -> HintsRuleSet:
    """Load rules and validate that every tool reference is in *known_tools*.

    Both source-tool keys (``tools`` mapping) and hint target tools
    (``Hint.tool``) are checked.  If any unknown tools are found, a single
    ``ValueError`` is raised that lists **all** of them in the message.

    Raises:
        FileNotFoundError: propagated from :func:`load_rules`.
        yaml.YAMLError: propagated from :func:`load_rules`.
        ValidationError: propagated from :func:`load_rules`.
        ValueError: if any source or target tool is not in *known_tools*.
    """
    rule_set = load_rules(path)

    unknown: set[str] = set()

    for source_tool, tool_hints in rule_set.tools.items():
        if source_tool not in known_tools:
            unknown.add(source_tool)
        for hint in tool_hints.hints:
            if hint.tool not in known_tools:
                unknown.add(hint.tool)

    if unknown:
        listed = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown tools referenced in hints rules file: {listed}")

    return rule_set
