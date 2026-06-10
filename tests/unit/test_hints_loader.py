"""Tests for the follow-up-hints Pydantic models + YAML loader (Sprint 15.1).

APIs under test:
- ``mcp_toolkit_py.hints.rules.Hint`` — single hint entry
- ``mcp_toolkit_py.hints.rules.ToolHints`` — per-source-tool container
- ``mcp_toolkit_py.hints.rules.HintsRuleSet`` — top-level document
- ``mcp_toolkit_py.hints.loader.load_rules(path)`` — parse YAML
- ``mcp_toolkit_py.hints.loader.load_rules_for_known_tools(path, known)``
  — parse + validate that every source tool key and every hint target is
  in the ``known`` set; raise otherwise with a clear message.

Design constraints:
- ``version`` is mandatory at the top level. Only ``1`` is accepted today;
  any other version raises so a future v2 cannot be silently mis-parsed.
- ``Hint.tool`` and ``Hint.rationale`` are required. ``when`` and
  ``arguments_template`` are optional.
- ``arguments_template`` values are strings (placeholder templates rendered
  later); we forbid nested dicts to keep the render layer simple.
- An empty ``tools: {}`` document is valid (e.g. during a roll-out where
  hints exist only for some tools).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError


def _import_models():
    from mcp_toolkit_py.hints import rules

    return rules


def _import_loader():
    from mcp_toolkit_py.hints import loader

    return loader


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────────────────────


class TestHintModel:
    def test_minimum_required_fields(self):
        m = _import_models()
        h = m.Hint(tool="ask_ot_mcp", rationale="Detailantwort")
        assert h.tool == "ask_ot_mcp"
        assert h.rationale == "Detailantwort"
        assert h.when is None
        assert h.arguments_template is None

    def test_full_fields(self):
        m = _import_models()
        h = m.Hint(
            tool="ask_ot_mcp",
            when="result.hits > 0",
            rationale="Detailantwort",
            arguments_template={"question": "Erkläre {result.hits[0].title}"},
        )
        assert h.when == "result.hits > 0"
        assert h.arguments_template == {"question": "Erkläre {result.hits[0].title}"}

    def test_missing_tool_raises(self):
        m = _import_models()
        with pytest.raises(ValidationError):
            m.Hint(rationale="x")  # type: ignore[call-arg]

    def test_missing_rationale_raises(self):
        m = _import_models()
        with pytest.raises(ValidationError):
            m.Hint(tool="x")  # type: ignore[call-arg]

    def test_arguments_template_rejects_nested_dict(self):
        """arguments_template values must be strings — no nested structures."""
        m = _import_models()
        with pytest.raises(ValidationError):
            m.Hint(
                tool="x",
                rationale="y",
                arguments_template={"q": {"nested": "no"}},  # type: ignore[dict-item]
            )

    def test_extra_fields_rejected(self):
        """Strict schema — typos in YAML should fail loudly, not silently drop."""
        m = _import_models()
        with pytest.raises(ValidationError):
            m.Hint(tool="x", rationale="y", whan="typo")  # type: ignore[call-arg]


class TestToolHintsModel:
    def test_empty_hints_list_valid(self):
        m = _import_models()
        th = m.ToolHints(hints=[])
        assert th.hints == []

    def test_with_hints(self):
        m = _import_models()
        th = m.ToolHints(hints=[{"tool": "a", "rationale": "b"}])
        assert len(th.hints) == 1
        assert th.hints[0].tool == "a"


class TestHintsRuleSetModel:
    def test_minimum_valid(self):
        m = _import_models()
        rs = m.HintsRuleSet(version=1, tools={})
        assert rs.version == 1
        assert rs.tools == {}

    def test_missing_version_raises(self):
        m = _import_models()
        with pytest.raises(ValidationError):
            m.HintsRuleSet(tools={})  # type: ignore[call-arg]

    def test_unknown_version_raises(self):
        """Forward-compat: a future v2 file must NOT be parsed as v1."""
        m = _import_models()
        with pytest.raises(ValidationError):
            m.HintsRuleSet(version=2, tools={})

    def test_tools_omitted_defaults_to_empty(self):
        """The ``tools`` field is optional and defaults to an empty mapping."""
        m = _import_models()
        rs = m.HintsRuleSet(version=1)
        assert rs.tools == {}


# ──────────────────────────────────────────────────────────────────────────────
# YAML loader — load_rules(path)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def valid_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "tools": {
                    "search_docs": {
                        "hints": [
                            {
                                "tool": "ask_ot_mcp",
                                "when": "result.hits > 0",
                                "rationale": "Detailantwort",
                                "arguments_template": {"question": "Erkläre"},
                            },
                            {
                                "tool": "search_docs",
                                "when": "result.hits == 0",
                                "rationale": "Breitere Suche",
                            },
                        ]
                    }
                },
            }
        )
    )
    return p


class TestLoadRules:
    def test_loads_valid_file(self, valid_yaml):
        loader = _import_loader()
        rs = loader.load_rules(valid_yaml)
        assert rs.version == 1
        assert "search_docs" in rs.tools
        assert len(rs.tools["search_docs"].hints) == 2
        first = rs.tools["search_docs"].hints[0]
        assert first.tool == "ask_ot_mcp"
        assert first.when == "result.hits > 0"
        assert first.arguments_template == {"question": "Erkläre"}

    def test_missing_file_raises_filenotfound(self, tmp_path: Path):
        loader = _import_loader()
        with pytest.raises(FileNotFoundError):
            loader.load_rules(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path):
        p = tmp_path / "bad.yaml"
        p.write_text("version: 1\ntools: {[broken")
        loader = _import_loader()
        with pytest.raises((yaml.YAMLError, ValueError)):
            loader.load_rules(p)

    def test_missing_required_field_raises_validation(self, tmp_path: Path):
        p = tmp_path / "no-rationale.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "tools": {"search_docs": {"hints": [{"tool": "x"}]}},
                }
            )
        )
        loader = _import_loader()
        with pytest.raises(ValidationError):
            loader.load_rules(p)

    def test_empty_tools_section_valid(self, tmp_path: Path):
        p = tmp_path / "empty.yaml"
        p.write_text(yaml.safe_dump({"version": 1, "tools": {}}))
        loader = _import_loader()
        rs = loader.load_rules(p)
        assert rs.tools == {}

    def test_accepts_pathlib_and_str(self, valid_yaml):
        loader = _import_loader()
        loader.load_rules(valid_yaml)
        loader.load_rules(str(valid_yaml))


# ──────────────────────────────────────────────────────────────────────────────
# Loader with known-tool validation
# ──────────────────────────────────────────────────────────────────────────────


class TestLoadRulesForKnownTools:
    def test_all_known_passes(self, valid_yaml):
        loader = _import_loader()
        rs = loader.load_rules_for_known_tools(
            valid_yaml, known_tools={"search_docs", "ask_ot_mcp"}
        )
        assert "search_docs" in rs.tools

    def test_unknown_source_tool_raises(self, valid_yaml):
        loader = _import_loader()
        with pytest.raises(ValueError, match="search_docs"):
            loader.load_rules_for_known_tools(valid_yaml, known_tools={"ask_ot_mcp"})

    def test_unknown_target_tool_raises(self, tmp_path: Path):
        p = tmp_path / "bad-target.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "tools": {
                        "search_docs": {
                            "hints": [
                                {
                                    "tool": "nonexistent_tool",
                                    "rationale": "should fail",
                                }
                            ]
                        }
                    },
                }
            )
        )
        loader = _import_loader()
        with pytest.raises(ValueError, match="nonexistent_tool"):
            loader.load_rules_for_known_tools(p, known_tools={"search_docs"})

    def test_error_message_lists_all_unknown(self, tmp_path: Path):
        """When multiple unknown tools are referenced, the error must list each one."""
        p = tmp_path / "many-bad.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "tools": {
                        "search_docs": {
                            "hints": [
                                {"tool": "ghost_a", "rationale": "x"},
                                {"tool": "ghost_b", "rationale": "y"},
                            ]
                        }
                    },
                }
            )
        )
        loader = _import_loader()
        with pytest.raises(ValueError) as exc:
            loader.load_rules_for_known_tools(p, known_tools={"search_docs"})
        msg = str(exc.value)
        assert "ghost_a" in msg
        assert "ghost_b" in msg

    def test_empty_rules_with_known_tools_passes(self, tmp_path: Path):
        """A rules.yaml with no entries is trivially valid against any known set."""
        p = tmp_path / "empty.yaml"
        p.write_text(yaml.safe_dump({"version": 1, "tools": {}}))
        loader = _import_loader()
        rs = loader.load_rules_for_known_tools(p, known_tools=set())
        assert rs.tools == {}
