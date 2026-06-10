"""Tests for the FollowupHintsMiddleware orchestrator (Sprint 15.4).

API under test:
    ``mcp_toolkit_py.hints.middleware.FollowupHintsMiddleware``

The middleware is **the** integration point: it owns a HintsRuleSet, checks
the env flag on every call, and runs the matcher to select hints that
apply. It does NOT render the response — that's 15.5. It returns a
``list[Hint]`` (possibly empty); the caller decides what to do with it.

Construction modes:
- ``FollowupHintsMiddleware(rules=<HintsRuleSet>)`` — preloaded rules
- ``FollowupHintsMiddleware(rules_path=<Path>, known_tools=<set[str]>)``
  — loads via ``load_rules_for_known_tools``
- Exactly one of ``rules`` / ``rules_path`` is required (TypeError otherwise)

Call API:
    middleware.select_hints(
        tool_name: str,
        request_arguments: dict,
        result: dict,
    ) -> list[Hint]

The matcher context built internally is:
    {"result": result, "request": {"arguments": request_arguments}}

Behavioral contracts:
1. If ``hints_enabled()`` returns False, ``select_hints`` ALWAYS returns []
   (flag check is first, before anything else).
2. If ``tool_name`` is not in the rule set, returns [].
3. Hints without a ``when`` clause always match (unconditional).
4. Hints with a ``when`` clause are evaluated against the context.
5. If a ``when`` clause raises ValueError (e.g. malformed expression that
   somehow got past loader), that hint is SKIPPED — not propagated. The
   middleware must NEVER crash a tool call due to a hint-config bug.
6. Hint order in the rule set is preserved in the output.
7. The context is never mutated by the middleware.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _import_middleware():
    from mcp_toolkit_py.hints import middleware

    return middleware


def _import_models():
    from mcp_toolkit_py.hints import rules

    return rules


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def enabled(monkeypatch):
    """Force the env flag ON for the duration of the test."""
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "true")


@pytest.fixture
def disabled(monkeypatch):
    """Force the env flag OFF (default) for the test."""
    monkeypatch.delenv("MCP_FOLLOWUP_HINTS_ENABLED", raising=False)


@pytest.fixture
def basic_rules():
    m = _import_models()
    return m.HintsRuleSet.model_validate(
        {
            "version": 1,
            "tools": {
                "search_docs": {
                    "hints": [
                        {
                            "tool": "ask_ot_mcp",
                            "when": "result.hits > 0",
                            "rationale": "Detailantwort",
                        },
                        {
                            "tool": "search_docs",
                            "when": "result.hits == 0",
                            "rationale": "Breitere Suche",
                        },
                    ]
                },
                "ask_ot_mcp": {
                    "hints": [
                        {
                            "tool": "graph_traverse",
                            "rationale": "Abhängigkeiten erkunden",
                        }
                    ]
                },
            },
        }
    )


@pytest.fixture
def yaml_rules_file(tmp_path: Path) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "tools": {
                    "search_docs": {"hints": [{"tool": "ask_ot_mcp", "rationale": "Detailantwort"}]}
                },
            }
        )
    )
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Construction
# ──────────────────────────────────────────────────────────────────────────────


class TestConstruction:
    def test_with_preloaded_rules(self, basic_rules):
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        assert mw is not None

    def test_with_rules_path_and_known_tools(self, yaml_rules_file):
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(
            rules_path=yaml_rules_file,
            known_tools={"search_docs", "ask_ot_mcp"},
        )
        assert mw is not None

    def test_neither_rules_nor_path_raises(self):
        mw_mod = _import_middleware()
        with pytest.raises((TypeError, ValueError)):
            mw_mod.FollowupHintsMiddleware()

    def test_both_rules_and_path_raises(self, basic_rules, yaml_rules_file):
        mw_mod = _import_middleware()
        with pytest.raises((TypeError, ValueError)):
            mw_mod.FollowupHintsMiddleware(
                rules=basic_rules,
                rules_path=yaml_rules_file,
                known_tools={"search_docs", "ask_ot_mcp"},
            )

    def test_rules_path_without_known_tools_raises(self, yaml_rules_file):
        """Loading from path requires known_tools for validation."""
        mw_mod = _import_middleware()
        with pytest.raises((TypeError, ValueError)):
            mw_mod.FollowupHintsMiddleware(rules_path=yaml_rules_file)


# ──────────────────────────────────────────────────────────────────────────────
# Flag-gating (top-most concern — must be checked first)
# ──────────────────────────────────────────────────────────────────────────────


class TestFlagGating:
    def test_flag_off_returns_empty(self, basic_rules, disabled):
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        result = mw.select_hints(tool_name="search_docs", request_arguments={}, result={"hits": 5})
        assert result == []

    def test_flag_off_short_circuits_before_rules_lookup(self, basic_rules, disabled, monkeypatch):
        """When the flag is off, the matcher must not be invoked at all
        (defends against an accidental crash in a `when` clause leaking out)."""
        from mcp_toolkit_py.hints import matcher as matcher_mod

        calls = []

        def fake_evaluate(*args, **kwargs):
            calls.append((args, kwargs))
            return True

        monkeypatch.setattr(matcher_mod, "evaluate", fake_evaluate)

        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        mw.select_hints(tool_name="search_docs", request_arguments={}, result={"hits": 5})
        assert calls == []

    def test_forced_off_returns_empty(self, basic_rules, monkeypatch):
        monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "forced_off")
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        assert (
            mw.select_hints(tool_name="search_docs", request_arguments={}, result={"hits": 5}) == []
        )


# ──────────────────────────────────────────────────────────────────────────────
# Tool lookup
# ──────────────────────────────────────────────────────────────────────────────


class TestToolLookup:
    def test_unknown_tool_returns_empty(self, basic_rules, enabled):
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        result = mw.select_hints(tool_name="not_in_rules", request_arguments={}, result={})
        assert result == []

    def test_known_tool_with_matching_hint(self, basic_rules, enabled):
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        result = mw.select_hints(
            tool_name="search_docs", request_arguments={"q": "x"}, result={"hits": 5}
        )
        assert len(result) == 1
        assert result[0].tool == "ask_ot_mcp"

    def test_known_tool_with_alternative_match(self, basic_rules, enabled):
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        result = mw.select_hints(
            tool_name="search_docs", request_arguments={"q": "x"}, result={"hits": 0}
        )
        assert len(result) == 1
        assert result[0].tool == "search_docs"  # "broader search" hint

    def test_known_tool_no_when_clause(self, basic_rules, enabled):
        """A hint without ``when`` is always selected."""
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        result = mw.select_hints(tool_name="ask_ot_mcp", request_arguments={}, result={})
        assert len(result) == 1
        assert result[0].tool == "graph_traverse"


# ──────────────────────────────────────────────────────────────────────────────
# When-clause evaluation
# ──────────────────────────────────────────────────────────────────────────────


class TestWhenEvaluation:
    def test_neither_when_matches_returns_empty(self, basic_rules, enabled):
        """If no when-clause matches, returns []."""
        # `result.hits > 0` AND `result.hits == 0` are mutually exclusive
        # — but if `hits` is missing, neither matches (missing-path → False).
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        result = mw.select_hints(tool_name="search_docs", request_arguments={}, result={})
        assert result == []

    def test_when_clause_uses_request_arguments(self, enabled):
        """The matcher context must expose request.arguments.X for hint conditions."""
        m = _import_models()
        rules = m.HintsRuleSet.model_validate(
            {
                "version": 1,
                "tools": {
                    "search_docs": {
                        "hints": [
                            {
                                "tool": "search_docs",
                                "when": "request.arguments.top_k > 5",
                                "rationale": "narrow",
                            }
                        ]
                    }
                },
            }
        )
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=rules)
        assert (
            len(
                mw.select_hints(
                    tool_name="search_docs",
                    request_arguments={"top_k": 10},
                    result={},
                )
            )
            == 1
        )
        assert (
            mw.select_hints(
                tool_name="search_docs",
                request_arguments={"top_k": 3},
                result={},
            )
            == []
        )


# ──────────────────────────────────────────────────────────────────────────────
# Malformed when clauses must not crash the middleware
# ──────────────────────────────────────────────────────────────────────────────


class TestMalformedWhenIsolation:
    def test_malformed_when_is_skipped_not_raised(self, enabled):
        m = _import_models()
        rules = m.HintsRuleSet.model_validate(
            {
                "version": 1,
                "tools": {
                    "search_docs": {
                        "hints": [
                            {
                                "tool": "ask_ot_mcp",
                                "when": "this is not a valid expression",
                                "rationale": "should be skipped silently",
                            },
                            {
                                "tool": "search_docs",
                                "rationale": "no when — should still match",
                            },
                        ]
                    }
                },
            }
        )
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=rules)
        # Must NOT raise. The broken hint is dropped, the valid one passes through.
        result = mw.select_hints(tool_name="search_docs", request_arguments={}, result={})
        assert len(result) == 1
        assert result[0].tool == "search_docs"

    def test_forbidden_root_in_when_is_skipped(self, enabled):
        m = _import_models()
        rules = m.HintsRuleSet.model_validate(
            {
                "version": 1,
                "tools": {
                    "search_docs": {
                        "hints": [
                            {
                                "tool": "ask_ot_mcp",
                                "when": "os.environ.PATH == 'x'",
                                "rationale": "should be skipped",
                            }
                        ]
                    }
                },
            }
        )
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=rules)
        assert mw.select_hints(tool_name="search_docs", request_arguments={}, result={}) == []


# ──────────────────────────────────────────────────────────────────────────────
# Order preservation + purity
# ──────────────────────────────────────────────────────────────────────────────


class TestOrderAndPurity:
    def test_hint_order_preserved(self, enabled):
        m = _import_models()
        rules = m.HintsRuleSet.model_validate(
            {
                "version": 1,
                "tools": {
                    "search_docs": {
                        "hints": [
                            {"tool": "first", "rationale": "1"},
                            {"tool": "second", "rationale": "2"},
                            {"tool": "third", "rationale": "3"},
                        ]
                    }
                },
            }
        )
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=rules)
        result = mw.select_hints(tool_name="search_docs", request_arguments={}, result={})
        assert [h.tool for h in result] == ["first", "second", "third"]

    def test_context_inputs_not_mutated(self, basic_rules, enabled):
        request_args = {"q": "x", "top_k": 5}
        result_dict = {"hits": 5, "items": [{"id": 1}]}
        snap_args = {"q": "x", "top_k": 5}
        snap_result = {"hits": 5, "items": [{"id": 1}]}

        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(rules=basic_rules)
        mw.select_hints(
            tool_name="search_docs",
            request_arguments=request_args,
            result=result_dict,
        )
        assert request_args == snap_args
        assert result_dict == snap_result


# ──────────────────────────────────────────────────────────────────────────────
# Path-loading integration
# ──────────────────────────────────────────────────────────────────────────────


class TestPathLoading:
    def test_loads_rules_from_yaml_path(self, yaml_rules_file, enabled):
        mw_mod = _import_middleware()
        mw = mw_mod.FollowupHintsMiddleware(
            rules_path=yaml_rules_file,
            known_tools={"search_docs", "ask_ot_mcp"},
        )
        result = mw.select_hints(tool_name="search_docs", request_arguments={}, result={})
        assert len(result) == 1
        assert result[0].tool == "ask_ot_mcp"

    def test_path_loading_validates_known_tools(self, tmp_path: Path, enabled):
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "tools": {
                        "search_docs": {"hints": [{"tool": "nonexistent", "rationale": "no"}]}
                    },
                }
            )
        )
        mw_mod = _import_middleware()
        with pytest.raises(ValueError, match="nonexistent"):
            mw_mod.FollowupHintsMiddleware(rules_path=bad, known_tools={"search_docs"})
