"""Follow-up hint emission for FastMCP tool responses.

Generic subpackage used by all knowledge MCPs (ot-knowledge, itil,
servicenow, fnt, searxng). Originally implemented inline in
``ot-knowledge-mcp`` (Sprint 15) and lifted here in Sprint 16 to avoid
drift across the 5 MCP repos.

Standard usage from an MCP server module::

    from mcp_toolkit_py.hints import install_followup_hints

    install_followup_hints(
        mcp,
        rules_path=Path(__file__).parent / "hints" / "rules.yaml",
        known_tools={name for name in mcp._tool_manager._tools
                     if not name.startswith("internal_")},
    )

Opt-in via the env flag ``MCP_FOLLOWUP_HINTS_ENABLED=true``. Kill-switch
``MCP_FOLLOWUP_HINTS_ENABLED=forced_off`` overrides any truthy value.

Each MCP ships its own ``hints/rules.yaml`` next to the package; the
loader validates every referenced tool name against the caller-supplied
``known_tools`` set, so YAML drift is caught at server boot.
"""

from mcp_toolkit_py.hints.flag import hints_enabled
from mcp_toolkit_py.hints.integration import install_followup_hints
from mcp_toolkit_py.hints.loader import load_rules, load_rules_for_known_tools
from mcp_toolkit_py.hints.middleware import FollowupHintsMiddleware
from mcp_toolkit_py.hints.render import (
    MAX_HINTS,
    append_hints_to_text,
    format_hints_meta,
    format_hints_text,
)
from mcp_toolkit_py.hints.rules import Hint, HintsRuleSet, ToolHints

__all__ = [
    "MAX_HINTS",
    "FollowupHintsMiddleware",
    "Hint",
    "HintsRuleSet",
    "ToolHints",
    "append_hints_to_text",
    "format_hints_meta",
    "format_hints_text",
    "hints_enabled",
    "install_followup_hints",
    "load_rules",
    "load_rules_for_known_tools",
]
