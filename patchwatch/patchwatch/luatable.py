"""Parse the Lua table constructors used by Blizzard_APIDocumentationGenerated.

Each generated file looks like::

    local Unit =
    {
        Name = "Unit",
        Type = "System",
        Functions = { { Name = "UnitHealth", Type = "Function", ... }, ... },
        ...
    };
    APIDocumentation:AddDocumentationTable(Unit);

Values are literals (strings, numbers, booleans, nil, nested tables) or, in a
few places, expressions such as ``Enum.ForbiddenAspect.ScriptBindings`` or
``Enum.A.B + Enum.A.C``.  Expressions are not evaluated; they are kept as
:class:`Expr` (a ``str`` subclass holding the normalised source text), which
is enough to compare two builds.

This is plain Python so patchwatch needs no Lua runtime.  The test suite
cross-checks it against a real Lua 5.1 (``lupa``) when that is installed.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .lualex import Token, tokenize


class Expr(str):
    """A non-literal value kept as normalised source text."""

    __slots__ = ()


class LuaParseError(ValueError):
    pass


_WS_RE = re.compile(r"\s+")
_END = Token("eof", "", -1)


class _Parser:
    def __init__(self, src: str) -> None:
        self.src = src
        self.toks: List[Token] = list(tokenize(src))
        self.i = 0

    # -- token helpers -------------------------------------------------
    def peek(self, k: int = 0) -> Token:
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else _END

    def next(self) -> Token:
        t = self.peek()
        self.i += 1
        return t

    def expect_op(self, op: str) -> Token:
        t = self.next()
        if t.kind != "op" or t.value != op:
            raise LuaParseError(f"expected {op!r} at offset {t.pos}, got {t.value!r}")
        return t

    def is_op(self, op: str, k: int = 0) -> bool:
        t = self.peek(k)
        return t.kind == "op" and t.value == op

    # -- grammar -------------------------------------------------------
    def parse_table(self) -> Any:
        self.expect_op("{")
        array: List[Any] = []
        hashed: Dict[Any, Any] = {}
        while True:
            if self.is_op("}"):
                self.next()
                break
            t = self.peek()
            if t.kind == "eof":
                raise LuaParseError("unterminated table")
            if self.is_op("["):
                self.next()
                key = self.parse_value(stop=("]",))
                self.expect_op("]")
                self.expect_op("=")
                hashed[key] = self.parse_value()
            elif t.kind == "name" and self.is_op("=", 1):
                self.next()
                self.next()
                hashed[t.value] = self.parse_value()
            else:
                array.append(self.parse_value())
            if self.is_op(",") or self.is_op(";"):
                self.next()
            elif not self.is_op("}"):
                t = self.peek()
                raise LuaParseError(f"expected ',' or '}}' at offset {t.pos}, got {t.value!r}")
        if not hashed:
            return array
        if array:
            for n, v in enumerate(array, 1):
                hashed[n] = v  # positional items win, as in Lua 5.1
        return hashed

    def parse_value(self, stop: Tuple[str, ...] = (",", ";", "}")) -> Any:
        t = self.peek()
        nxt = self.peek(1)
        simple_end = nxt.kind == "eof" or (nxt.kind == "op" and nxt.value in stop)
        if t.kind == "op" and t.value == "{":
            return self.parse_table()
        if simple_end:
            if t.kind == "string":
                self.next()
                return t.value
            if t.kind == "number":
                self.next()
                return _number(t.value)
            if t.kind == "keyword" and t.value in ("true", "false", "nil"):
                self.next()
                return {"true": True, "false": False, "nil": None}[t.value]
        if t.kind == "op" and t.value == "-" and self.peek(1).kind == "number":
            after = self.peek(2)
            if after.kind == "eof" or (after.kind == "op" and after.value in stop):
                self.next()
                return -_number(self.next().value)
        return self.parse_expr(stop)

    def parse_expr(self, stop: Tuple[str, ...]) -> Expr:
        """Consume tokens up to a top-level stop token; keep the source text."""
        first = self.peek()
        if first.kind == "op" and first.value not in ("-", "#", "(", "{", "~"):
            raise LuaParseError(f"unexpected {first.value!r} at offset {first.pos}")
        start = first.pos
        depth = 0
        last_end = start
        while True:
            t = self.peek()
            if t.kind == "eof":
                break
            if t.kind == "bad":
                raise LuaParseError(f"unexpected character {t.value!r} at offset {t.pos}")
            if t.kind == "op":
                if depth == 0 and t.value in stop:
                    break
                if depth == 0 and t.value == "=":
                    raise LuaParseError(f"unexpected '=' at offset {t.pos}")
                if t.value in "({[":
                    depth += 1
                elif t.value in ")}]":
                    if depth == 0:
                        break
                    depth -= 1
            self.next()
            last_end = self._token_end(t)
        if last_end <= start:
            raise LuaParseError(f"empty value at offset {start}")
        return Expr(_WS_RE.sub(" ", self.src[start:last_end]).strip())

    def _token_end(self, t: Token) -> int:
        # Strings are decoded, so find the end from the next token's start.
        nxt = self.peek()
        if nxt.kind != "eof":
            end = nxt.pos
        else:
            end = len(self.src)
        # trim trailing whitespace/comments between tokens
        seg = self.src[t.pos:end]
        cut = seg.find("--")
        if cut > 0 and t.kind != "string":
            seg = seg[:cut]
        return t.pos + len(seg.rstrip())


def _number(text: str) -> Any:
    try:
        if text.lower().startswith("0x"):
            return int(text, 16)
        if any(c in text for c in ".eE"):
            f = float(text)
            return int(f) if f.is_integer() and "." not in text else f
        return int(text)
    except ValueError:
        return Expr(text)


def parse_value(src: str) -> Any:
    """Parse a single Lua value (used by tests)."""
    p = _Parser(src)
    v = p.parse_value(stop=())
    return v


def parse_documentation_file(src: str) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Parse one generated documentation file.

    Returns ``(tables, registered, errors)`` where ``tables`` maps each top
    level ``local NAME = { ... }`` (or global assignment) to its parsed value,
    ``registered`` lists the names passed to
    ``APIDocumentation:AddDocumentationTable(NAME)`` in order, and ``errors``
    lists parse problems (the parser skips a broken table and keeps going).
    """
    p = _Parser(src)
    tables: Dict[str, Any] = {}
    registered: List[str] = []
    errors: List[str] = []
    while p.peek().kind != "eof":
        t = p.peek()
        # local NAME = {   |   NAME = {
        if t.kind == "keyword" and t.value == "local":
            p.next()
            continue
        if t.kind == "name" and p.is_op("=", 1) and p.is_op("{", 2):
            name = t.value
            p.next()
            p.next()
            start = p.i
            try:
                tables[name] = p.parse_table()
            except LuaParseError as exc:
                errors.append(f"{name}: {exc}")
                p.i = _skip_balanced(p.toks, start)
            continue
        if (t.kind == "name" and t.value == "APIDocumentation" and p.is_op(":", 1)
                and p.peek(2).value == "AddDocumentationTable" and p.is_op("(", 3)
                and p.peek(4).kind == "name"):
            registered.append(p.peek(4).value)
            p.i += 5
            continue
        p.next()
    return tables, registered, errors


def _skip_balanced(toks: List[Token], start: int) -> int:
    depth = 0
    for j in range(start, len(toks)):
        t = toks[j]
        if t.kind == "op" and t.value == "{":
            depth += 1
        elif t.kind == "op" and t.value == "}":
            depth -= 1
            if depth <= 0:
                return j + 1
    return len(toks)


def registered_tables(src: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return the documentation tables a file registers, plus parse errors.

    Falls back to every top-level table when the file has no
    ``AddDocumentationTable`` call (older or hand-made fixtures).
    """
    tables, registered, errors = parse_documentation_file(src)
    names: List[str] = registered or list(tables)
    out: List[Dict[str, Any]] = []
    for n in names:
        v: Optional[Any] = tables.get(n)
        if isinstance(v, dict):
            out.append(v)
        elif isinstance(v, list) and not v:
            out.append({})
        elif n in tables:
            errors.append(f"{n}: registered value is not a keyed table")
    return out, errors
