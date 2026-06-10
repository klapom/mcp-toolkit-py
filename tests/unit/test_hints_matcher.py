"""Tests for the follow-up-hints conditional matcher (Sprint 15.3).

API under test:
    ``mcp_toolkit_py.hints.matcher.evaluate(expression, context) -> bool``

The matcher decides whether a hint's ``when`` clause applies given the
post-call context. It evaluates a **sandboxed** mini-DSL — NO Python
``eval`` is permitted. The grammar is deliberately tiny so we can
implement it with a regex-based parser, no third-party dep:

    comparison := <path> <op> <literal>
    op         := == | != | < | <= | > | >=
    path       := identifier ("." identifier)*
    literal    := integer | quoted_string | true | false

Roots permitted in ``path``: ``result``, ``request``. Anything else
raises. The first identifier is the root; subsequent ones are dict-key
or attribute lookups against the corresponding context entry.

Safety guarantees the tests enforce:
- No function calls, no dunder access, no attribute-name traversal that
  could reach Python internals (no ``__class__`` etc.).
- Missing intermediate path returns False (NOT KeyError) so a hint
  silently doesn't apply.
- Type mismatches on comparisons return False (don't crash on string vs.
  int comparison).
- ``evaluate(None, ctx)`` returns True — "no condition" means "always".
- ``evaluate("", ctx)`` returns True — same reason.
"""

from __future__ import annotations

import pytest


def _import_matcher():
    from mcp_toolkit_py.hints import matcher

    return matcher


# ── empty / None expressions = unconditional match ───────────────────────────


def test_none_expression_returns_true():
    assert _import_matcher().evaluate(None, {"result": {}}) is True


def test_empty_string_returns_true():
    assert _import_matcher().evaluate("", {"result": {}}) is True


def test_whitespace_only_returns_true():
    assert _import_matcher().evaluate("   ", {"result": {}}) is True


# ── integer comparison ───────────────────────────────────────────────────────


def test_gt_truthy():
    assert _import_matcher().evaluate("result.hits > 0", {"result": {"hits": 5}}) is True


def test_gt_falsy():
    assert _import_matcher().evaluate("result.hits > 0", {"result": {"hits": 0}}) is False


def test_ge_boundary():
    m = _import_matcher()
    assert m.evaluate("result.hits >= 1", {"result": {"hits": 1}}) is True
    assert m.evaluate("result.hits >= 1", {"result": {"hits": 0}}) is False


def test_lt():
    m = _import_matcher()
    assert m.evaluate("result.hits < 10", {"result": {"hits": 5}}) is True
    assert m.evaluate("result.hits < 10", {"result": {"hits": 10}}) is False


def test_le():
    m = _import_matcher()
    assert m.evaluate("result.hits <= 10", {"result": {"hits": 10}}) is True
    assert m.evaluate("result.hits <= 10", {"result": {"hits": 11}}) is False


def test_eq_int():
    m = _import_matcher()
    assert m.evaluate("result.hits == 0", {"result": {"hits": 0}}) is True
    assert m.evaluate("result.hits == 0", {"result": {"hits": 1}}) is False


def test_ne_int():
    m = _import_matcher()
    assert m.evaluate("result.hits != 0", {"result": {"hits": 1}}) is True
    assert m.evaluate("result.hits != 0", {"result": {"hits": 0}}) is False


# ── string comparison ────────────────────────────────────────────────────────


def test_eq_string_double_quotes():
    m = _import_matcher()
    ctx = {"result": {"status": "ok"}}
    assert m.evaluate('result.status == "ok"', ctx) is True
    assert m.evaluate('result.status == "fail"', ctx) is False


def test_eq_string_single_quotes():
    m = _import_matcher()
    ctx = {"result": {"status": "ok"}}
    assert m.evaluate("result.status == 'ok'", ctx) is True


# ── boolean literals ─────────────────────────────────────────────────────────


def test_eq_true():
    m = _import_matcher()
    assert m.evaluate("result.success == true", {"result": {"success": True}}) is True
    assert m.evaluate("result.success == true", {"result": {"success": False}}) is False


def test_eq_false():
    m = _import_matcher()
    assert m.evaluate("result.success == false", {"result": {"success": False}}) is True


# ── dotted paths through nested dicts ────────────────────────────────────────


def test_nested_path():
    m = _import_matcher()
    ctx = {"result": {"metadata": {"confidence": 80}}}
    assert m.evaluate("result.metadata.confidence > 50", ctx) is True
    assert m.evaluate("result.metadata.confidence > 90", ctx) is False


# ── safety: missing path returns False (no KeyError) ─────────────────────────


def test_missing_top_level_key_returns_false():
    m = _import_matcher()
    assert m.evaluate("result.hits > 0", {"result": {}}) is False


def test_missing_nested_key_returns_false():
    m = _import_matcher()
    assert m.evaluate("result.meta.score > 0", {"result": {}}) is False


def test_missing_root_returns_false():
    """Root present but path goes through nonexistent intermediate."""
    m = _import_matcher()
    assert m.evaluate("result.meta.score > 0", {"result": {"hits": 0}}) is False


def test_missing_context_root_returns_false():
    """If even ``result`` is missing from the ctx (post-call shouldn't happen,
    but defensive), we return False rather than blow up."""
    m = _import_matcher()
    assert m.evaluate("result.hits > 0", {}) is False


# ── safety: type-mismatch returns False ──────────────────────────────────────


def test_type_mismatch_string_vs_int_returns_false():
    m = _import_matcher()
    ctx = {"result": {"hits": "five"}}
    assert m.evaluate("result.hits > 0", ctx) is False


def test_type_mismatch_int_vs_string_returns_false():
    m = _import_matcher()
    assert m.evaluate('result.count == "ok"', {"result": {"count": 5}}) is False


# ── safety: forbidden constructs raise (NOT eval'd, NOT silently False) ──────


def test_unknown_root_raises():
    """Only ``result`` and ``request`` are accepted as path roots — anything
    else is almost certainly a typo or attack, raise loudly."""
    m = _import_matcher()
    with pytest.raises(ValueError, match="root"):
        m.evaluate("os.path > 0", {"result": {}})


def test_dunder_access_raises():
    """``result.__class__`` etc. must NOT be reachable."""
    m = _import_matcher()
    with pytest.raises(ValueError):
        m.evaluate("result.__class__ == 'dict'", {"result": {}})


def test_function_call_syntax_raises():
    m = _import_matcher()
    with pytest.raises(ValueError):
        m.evaluate("result.hits.bit_length() > 0", {"result": {"hits": 1}})


def test_import_attempt_raises():
    m = _import_matcher()
    with pytest.raises(ValueError):
        m.evaluate("__import__('os').system('rm') > 0", {"result": {}})


def test_invalid_syntax_raises_with_helpful_message():
    m = _import_matcher()
    with pytest.raises(ValueError) as exc:
        m.evaluate("this is not an expression at all", {"result": {}})
    # Message should mention what couldn't be parsed
    assert "expression" in str(exc.value).lower() or "parse" in str(exc.value).lower()


def test_missing_operator_raises():
    m = _import_matcher()
    with pytest.raises(ValueError):
        m.evaluate("result.hits 5", {"result": {"hits": 5}})


# ── request root ─────────────────────────────────────────────────────────────


def test_request_root_works():
    """``request`` is the second allowed root — e.g. for routing on input."""
    m = _import_matcher()
    ctx = {"result": {}, "request": {"arguments": {"top_k": 10}}}
    assert m.evaluate("request.arguments.top_k > 5", ctx) is True
    assert m.evaluate("request.arguments.top_k > 20", ctx) is False


# ── purity: evaluate must not mutate the context ─────────────────────────────


def test_context_not_mutated():
    m = _import_matcher()
    ctx = {"result": {"hits": 5, "meta": {"x": 1}}}
    snapshot = {"result": {"hits": 5, "meta": {"x": 1}}}
    m.evaluate("result.hits > 0", ctx)
    m.evaluate("result.meta.x == 1", ctx)
    assert ctx == snapshot
