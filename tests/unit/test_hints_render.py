"""Tests for the follow-up-hints render helpers (Sprint 15.5).

APIs under test:
    ``mcp_toolkit_py.hints.render.format_hints_text(hints) -> str``
    ``mcp_toolkit_py.hints.render.format_hints_meta(hints) -> list[dict]``
    ``mcp_toolkit_py.hints.render.append_hints_to_text(text, hints) -> str``
    ``mcp_toolkit_py.hints.render.MAX_HINTS`` — int constant (3)

These produce the LLM-facing text block and the structured ``_meta``
payload. Both are deterministic, capped at ``MAX_HINTS``, and never raise
on well-formed input.

Design constraints:
- ``MAX_HINTS == 3`` — guards against token-bloat.
- Hints are emitted in input-list order (already pre-sorted by middleware).
- Text-block is German (consistent with the live system instructions);
  the prefix line is exactly ``"Mögliche nächste Schritte:"``.
- Text-block uses a numbered list ``"1. "``, ``"2. "``, ``"3. "``.
- The separator before the block is ``"\n\n---\n"`` (markdown rule),
  appended to any existing text that already had content.
- Empty hint list = no-op for ALL three functions.
- ``format_hints_meta`` returns plain dicts (JSON-serialisable). ``when``
  is NEVER exposed (internal rule field). ``arguments_template`` is
  included only when non-None.
"""

from __future__ import annotations


def _import_render():
    from mcp_toolkit_py.hints import render

    return render


def _import_models():
    from mcp_toolkit_py.hints import rules

    return rules


def _hint(tool: str, rationale: str, args: dict[str, str] | None = None):
    m = _import_models()
    kwargs: dict = {"tool": tool, "rationale": rationale}
    if args is not None:
        kwargs["arguments_template"] = args
    return m.Hint(**kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# MAX_HINTS constant
# ──────────────────────────────────────────────────────────────────────────────


def test_max_hints_constant_is_three():
    r = _import_render()
    assert r.MAX_HINTS == 3


# ──────────────────────────────────────────────────────────────────────────────
# format_hints_text
# ──────────────────────────────────────────────────────────────────────────────


class TestFormatHintsText:
    def test_empty_returns_empty_string(self):
        r = _import_render()
        assert r.format_hints_text([]) == ""

    def test_single_hint(self):
        r = _import_render()
        out = r.format_hints_text([_hint("ask_ot_mcp", "Detailantwort")])
        assert "Mögliche nächste Schritte:" in out
        assert "1. ask_ot_mcp" in out
        assert "Detailantwort" in out

    def test_two_hints_numbered_in_order(self):
        r = _import_render()
        out = r.format_hints_text(
            [
                _hint("ask_ot_mcp", "Detailantwort"),
                _hint("graph_traverse", "Abhängigkeiten"),
            ]
        )
        # Check ordering — line "1." comes before line "2."
        i1 = out.index("1. ask_ot_mcp")
        i2 = out.index("2. graph_traverse")
        assert i1 < i2

    def test_caps_at_max_hints(self):
        r = _import_render()
        many = [_hint(f"tool_{i}", f"rat_{i}") for i in range(10)]
        out = r.format_hints_text(many)
        assert "1. tool_0" in out
        assert "2. tool_1" in out
        assert "3. tool_2" in out
        assert "tool_3" not in out  # 4th hint and beyond dropped
        assert "tool_9" not in out

    def test_text_does_not_expose_when_field(self):
        """Even if hint has a ``when`` clause, the rendered text must not include it
        — that's an internal rule-engine concern, not user-facing."""
        m = _import_models()
        h = m.Hint(tool="x", rationale="r", when="result.hits > 0")
        out = _import_render().format_hints_text([h])
        assert "result.hits" not in out
        assert "when" not in out.lower()


# ──────────────────────────────────────────────────────────────────────────────
# format_hints_meta
# ──────────────────────────────────────────────────────────────────────────────


class TestFormatHintsMeta:
    def test_empty_returns_empty_list(self):
        r = _import_render()
        assert r.format_hints_meta([]) == []

    def test_single_hint_serialisation(self):
        r = _import_render()
        out = r.format_hints_meta([_hint("ask_ot_mcp", "Detailantwort")])
        assert len(out) == 1
        assert out[0]["tool"] == "ask_ot_mcp"
        assert out[0]["rationale"] == "Detailantwort"
        # arguments_template absent → key NOT included (clean payload)
        assert "arguments_template" not in out[0]

    def test_with_arguments_template(self):
        r = _import_render()
        out = r.format_hints_meta([_hint("ask_ot_mcp", "Detail", {"question": "Erkläre"})])
        assert out[0]["arguments_template"] == {"question": "Erkläre"}

    def test_caps_at_max_hints(self):
        r = _import_render()
        many = [_hint(f"tool_{i}", f"rat_{i}") for i in range(5)]
        out = r.format_hints_meta(many)
        assert len(out) == 3
        assert [d["tool"] for d in out] == ["tool_0", "tool_1", "tool_2"]

    def test_when_field_never_exposed(self):
        m = _import_models()
        h = m.Hint(tool="x", rationale="r", when="result.hits > 0")
        out = _import_render().format_hints_meta([h])
        assert "when" not in out[0]

    def test_output_is_plain_dicts_not_pydantic(self):
        """The output must be JSON-serialisable plain dicts, not BaseModel objects."""
        import json

        r = _import_render()
        out = r.format_hints_meta([_hint("a", "r", {"q": "x"}), _hint("b", "r2")])
        # Must round-trip through json with no custom encoder
        json.dumps(out)
        # And each item must be a plain dict
        for item in out:
            assert isinstance(item, dict)


# ──────────────────────────────────────────────────────────────────────────────
# append_hints_to_text
# ──────────────────────────────────────────────────────────────────────────────


class TestAppendHintsToText:
    def test_empty_hints_returns_input_unchanged(self):
        r = _import_render()
        assert r.append_hints_to_text("hello world", []) == "hello world"

    def test_empty_text_with_hints(self):
        r = _import_render()
        out = r.append_hints_to_text("", [_hint("x", "y")])
        # No separator on empty text — just the block itself
        assert out.startswith("Mögliche nächste Schritte:")
        assert "1. x" in out
        assert "y" in out

    def test_text_with_hints_uses_separator(self):
        r = _import_render()
        out = r.append_hints_to_text("answer text", [_hint("x", "y")])
        assert out.startswith("answer text")
        # Separator (markdown rule) appears between content and hint block
        assert "\n\n---\n" in out
        # Hint block follows
        assert "Mögliche nächste Schritte:" in out
        # And the hint itself
        assert "1. x" in out

    def test_trailing_whitespace_stripped_before_append(self):
        """Existing trailing whitespace/newlines should not stack up."""
        r = _import_render()
        out = r.append_hints_to_text("answer\n\n\n", [_hint("x", "y")])
        # No 4+ consecutive newlines anywhere
        assert "\n\n\n\n" not in out
        assert "Mögliche nächste Schritte:" in out

    def test_multiline_text_preserved(self):
        r = _import_render()
        text = "line 1\nline 2\nline 3"
        out = r.append_hints_to_text(text, [_hint("x", "y")])
        assert "line 1\nline 2\nline 3" in out

    def test_appended_block_uses_same_format_as_format_hints_text(self):
        """append_hints_to_text must use format_hints_text — single source of truth
        for the rendered block, so future tweaks stay consistent."""
        r = _import_render()
        hints = [_hint("a", "b")]
        block = r.format_hints_text(hints)
        appended = r.append_hints_to_text("text", hints)
        assert block in appended
