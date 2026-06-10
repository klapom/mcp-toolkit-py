"""Sandboxed when-expression evaluator for follow-up hints (Sprint 15.3).

Grammar:
    comparison ::= path op literal
    op         ::= == | != | <= | >= | < | >
    path       ::= identifier ("." identifier)*
    literal    ::= integer | quoted_string | "true" | "false"

Roots: only ``result`` and ``request`` are allowed.
No ``eval``, no ``exec``, no ``compile`` — pure regex + explicit walker.
"""

from __future__ import annotations

import operator
import re
from typing import Any

# Allowed path roots
_ALLOWED_ROOTS = {"result", "request"}

# Operator dispatch — keys must match the regex alternatives in _EXPR_RE.
_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}

# Regex: path  op  literal
# Operator alternatives ordered longest-first to avoid `<` shadowing `<=`.
_EXPR_RE = re.compile(
    r"^\s*"
    r"([A-Za-z_][A-Za-z0-9_.]*)"  # group 1 — dotted path
    r"\s*(==|!=|<=|>=|<|>)\s*"  # group 2 — operator
    r"(.*?)"  # group 3 — literal (stripped later)
    r"\s*$"
)

# A valid identifier segment: must not start with underscore
_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _parse_path(path_str: str) -> list[str]:
    """Split and validate a dotted path string.

    Raises ValueError if any segment is invalid (leading underscore, parens, etc.).
    """
    # Reject anything with parentheses (function calls)
    if "(" in path_str or ")" in path_str:
        raise ValueError(f"function calls are not allowed in expression path: {path_str!r}")

    segments = path_str.split(".")
    for seg in segments:
        if not seg:
            raise ValueError(f"empty segment in path: {path_str!r}")
        if seg.startswith("_"):
            raise ValueError(
                f"access to private/dunder attribute {seg!r} is not allowed in path: {path_str!r}"
            )
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", seg):
            raise ValueError(f"invalid identifier segment {seg!r} in path: {path_str!r}")
    return segments


def _parse_literal(lit_str: str) -> int | str | bool:
    """Parse a literal token: integer, quoted string, or boolean keyword.

    Raises ValueError if the literal is not recognised.
    """
    s = lit_str.strip()

    # Reject function calls or parens inside the literal
    if "(" in s or ")" in s:
        raise ValueError(f"function calls are not allowed in literal: {s!r}")

    # Boolean keywords (check before int so 'true'/'false' are not mistaken)
    if s == "true":
        return True
    if s == "false":
        return False

    # Integer
    try:
        return int(s)
    except ValueError:
        pass

    # Quoted string (single or double quotes)
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]

    raise ValueError(f"cannot parse literal: {s!r}")


def _resolve_path(segments: list[str], context: dict[str, Any]) -> object:
    """Walk *segments* through *context* (dict-only traversal).

    Returns a sentinel ``_MISSING`` object if any intermediate key is absent
    or the current node is not a dict.
    """
    node: object = context
    for seg in segments:
        if not isinstance(node, dict):
            return _MISSING
        node = node.get(seg, _MISSING)
        if node is _MISSING:
            return _MISSING
    return node


class _MissingSentinel:
    """Unique sentinel for missing path values."""

    __slots__ = ()


_MISSING = _MissingSentinel()


def evaluate(expression: str | None, context: dict[str, Any]) -> bool:
    """Evaluate *expression* against *context* in a sandboxed fashion.

    Parameters
    ----------
    expression:
        A ``when`` clause string as defined in the Sprint-15 grammar, or
        ``None`` / empty string for an unconditional match.
    context:
        Dict with keys ``result`` and/or ``request``.  Must not be mutated.

    Returns
    -------
    bool
        ``True`` if the expression matches, ``False`` otherwise.

    Raises
    ------
    ValueError
        For any forbidden construct, unknown root, or parse failure.
    """
    # Empty / None → unconditional
    if expression is None:
        return True
    stripped = expression.strip()
    if not stripped:
        return True

    # Reject dunder shortcuts before regex (e.g. __import__(...))
    if "__" in stripped:
        raise ValueError(f"dunder/private constructs are not allowed in expression: {expression!r}")

    # Reject parentheses (function calls) at top level before regex
    if "(" in stripped or ")" in stripped:
        raise ValueError(f"function calls are not allowed in expression: {expression!r}")

    # Parse
    match = _EXPR_RE.match(stripped)
    if not match:
        raise ValueError(
            f"could not parse expression: {expression!r} — expected: <path> <op> <literal>"
        )

    path_str, op, lit_str = match.group(1), match.group(2), match.group(3)

    # Validate and split path
    segments = _parse_path(path_str)

    # Check root
    root = segments[0]
    if root not in _ALLOWED_ROOTS:
        raise ValueError(
            f"unknown root {root!r} in expression — allowed roots: {sorted(_ALLOWED_ROOTS)}"
        )

    # Parse literal
    literal = _parse_literal(lit_str)

    # Resolve path in context (no mutation)
    value = _resolve_path(segments, context)

    # Missing path → False (no crash)
    if isinstance(value, _MissingSentinel):
        return False

    # Type-safety: compare only when types match exactly.
    # In Python bool is a subclass of int, so we must distinguish explicitly.
    lv_type = type(value)
    rv_type = type(literal)

    if lv_type is not rv_type:
        # Allow int comparisons against int only; bool vs int is a mismatch too
        # because True == 1 in Python but semantically different.
        return False

    # Perform comparison via module-level operator dispatch.
    # `value` is statically `object` (path-walker can't narrow it) but we've
    # asserted type equality above, so the operator is well-defined at runtime.
    try:
        return bool(_OPS[op](value, literal))  # type: ignore[arg-type]
    except TypeError:
        return False
