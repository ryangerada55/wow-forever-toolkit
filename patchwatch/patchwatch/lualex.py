"""A small, tolerant Lua 5.1 lexer.

It is used for two jobs:

* parsing Blizzard's generated API documentation tables (see luatable.py), and
* scanning addon source for referenced API names (see scan.py).

It never raises on malformed input: an unterminated string or stray character
becomes a one-character "bad" token and lexing continues, so a broken addon
file still yields the references the scanner can find.
"""
from __future__ import annotations

import bisect
import re
from typing import Iterator, List, NamedTuple

_TOKEN_RE = re.compile(
    r"""
     (?P<ws>\s+)
    |(?P<comment>--(?:\[(?P<ceq>=*)\[[\s\S]*?\](?P=ceq)\]|[^\n]*))
    |(?P<lstr>\[(?P<seq>=*)\[[\s\S]*?\](?P=seq)\])
    |(?P<str>"(?:[^"\\\n]|\\[\s\S])*"|'(?:[^'\\\n]|\\[\s\S])*')
    |(?P<num>0[xX][0-9a-fA-F]*(?:\.[0-9a-fA-F]*)?(?:[pP][+-]?\d+)?
            |(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
    |(?P<name>[A-Za-z_][A-Za-z0-9_]*)
    |(?P<op>\.\.\.|\.\.|==|~=|<=|>=|<<|>>|//|::|[-+*/%^\#&~|<>=(){}\[\];:,.])
    |(?P<bad>[\s\S])
    """,
    re.VERBOSE,
)

KEYWORDS = frozenset(
    """and break do else elseif end false for function goto if in local nil not
    or repeat return then true until while""".split()
)


class Token(NamedTuple):
    kind: str  # 'name', 'keyword', 'string', 'number', 'op', 'bad'
    value: str  # decoded value for strings, source text otherwise
    pos: int  # offset of the token in the source


_ESCAPES = {
    "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
    "v": "\v", "\\": "\\", '"': '"', "'": "'", "\n": "\n",
}


def decode_string(literal: str) -> str:
    """Decode a quoted or long-bracket Lua string literal to its value."""
    if literal.startswith("["):
        eq = literal.index("[", 1) + 1
        body = literal[eq:len(literal) - eq]
        # a newline right after the opening bracket is skipped by Lua
        if body.startswith("\r\n"):
            body = body[2:]
        elif body.startswith("\n"):
            body = body[1:]
        return body
    body = literal[1:-1]
    if "\\" not in body:
        return body
    out: List[str] = []
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        e = body[i + 1]
        if e in _ESCAPES:
            out.append(_ESCAPES[e])
            i += 2
        elif e.isdigit():
            j = i + 1
            while j < n and j < i + 4 and body[j].isdigit():
                j += 1
            out.append(chr(int(body[i + 1:j]) % 256))
            i = j
        elif e == "x" and i + 3 < n + 1:
            try:
                out.append(chr(int(body[i + 2:i + 4], 16)))
                i += 4
            except ValueError:
                out.append(e)
                i += 2
        elif e == "z":
            i += 2
            while i < n and body[i].isspace():
                i += 1
        elif e == "u" and i + 2 < n and body[i + 2] == "{":
            end = body.find("}", i + 3)
            try:
                out.append(chr(int(body[i + 3:end], 16)))
                i = end + 1
            except ValueError:
                out.append(e)
                i += 2
        else:
            out.append(e)
            i += 2
    return "".join(out)


def tokenize(src: str, keep_comments: bool = False) -> Iterator[Token]:
    """Yield tokens from Lua source. Whitespace (and comments) are skipped."""
    for m in _TOKEN_RE.finditer(src):
        kind = m.lastgroup
        if kind == "ws":
            continue
        text = m.group(kind)
        if kind == "comment":
            if keep_comments:
                yield Token("comment", text, m.start())
            continue
        if kind == "name":
            yield Token("keyword" if text in KEYWORDS else "name", text, m.start())
        elif kind in ("str", "lstr"):
            yield Token("string", decode_string(text), m.start())
        elif kind == "num":
            yield Token("number", text, m.start())
        elif kind == "op":
            yield Token("op", text, m.start())
        else:
            yield Token("bad", text, m.start())


class LineIndex:
    """Map character offsets to 1-based line numbers."""

    def __init__(self, src: str) -> None:
        self._starts = [0]
        idx = src.find("\n")
        while idx != -1:
            self._starts.append(idx + 1)
            idx = src.find("\n", idx + 1)

    def line(self, pos: int) -> int:
        return bisect.bisect_right(self._starts, pos)
