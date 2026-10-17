"""Cross-check the pure-Python parser against a real Lua 5.1 (lupa), when installed.

Set PATCHWATCH_LUPA_DOCS_DIR to a Blizzard_APIDocumentationGenerated folder
(or several, separated by os.pathsep) to check real documentation files too.
"""
import os
from pathlib import Path

import pytest
from conftest import FIX

from patchwatch.luatable import registered_tables

lupa = pytest.importorskip("lupa")
from lupa_helper import lua_load_file, normalise  # noqa: E402


def _files():
    files = sorted((FIX / "docs_old").glob("*.lua")) + sorted((FIX / "docs_new").glob("*.lua"))
    for d in filter(None, os.environ.get("PATCHWATCH_LUPA_DOCS_DIR", "").split(os.pathsep)):
        files += sorted(Path(d).glob("*.lua"))
    return files


@pytest.mark.parametrize("path", _files(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_parser_matches_lua(path):
    src = path.read_text(encoding="utf-8", errors="replace")
    ours, errors = registered_tables(src)
    assert not errors
    assert normalise(ours) == normalise(lua_load_file(src))
