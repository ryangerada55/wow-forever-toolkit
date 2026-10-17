"""Everything patchwatch extracts from one build, and the comparison of two builds."""
from __future__ import annotations

import gzip
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from . import __version__
from .apidocs import DOC_DIR, build_model, diff_models, summarize_model
from .lualex import tokenize
from .mirror import Build, DirSource, Mirror, interface_number

# Bump when the snapshot content changes so cached JSON is rebuilt.
SNAPSHOT_FORMAT = 2
DEPRECATED_DIR = "Interface/AddOns/Blizzard_Deprecated"
CONSTANTS_DIR = "Interface/AddOns/Blizzard_ProjectConstants"

_CONST_RE = re.compile(r"(?:^|;)\s*([A-Z][A-Z0-9_]*)\s*=\s*([^;\n]+?)\s*(?=;|$)", re.M)
_TOC_LINE_RE = re.compile(r"^([^#\s][^\[\n]*?)\s*((?:\[[^\]]*\]\s*)*)$")


def shim_names(src: str) -> List[str]:
    """Global names a Blizzard_Deprecated file defines (``X = ...``, ``C_Y.Z = ...``, ``function X()``).

    Uses the Lua lexer, so names in comments (the SpellBook transition guide is
    one long comment) are ignored, and chains rooted at a local are skipped.
    """
    toks = list(tokenize(src))
    n = len(toks)
    locals_: set = set()
    names: set = set()

    def op(j: int, v: str) -> bool:
        return 0 <= j < n and toks[j].kind == "op" and toks[j].value == v

    depth = 0  # inside a table constructor, NAME = is a field key
    for i, t in enumerate(toks):
        if t.kind == "op" and t.value == "{":
            depth += 1
            continue
        if t.kind == "op" and t.value == "}":
            depth = max(0, depth - 1)
            continue
        if t.kind == "keyword" and t.value == "function":
            # parameters are locals
            j = i + 1
            while j < n and not op(j, "("):
                j += 1
            j += 1
            while j < n and not op(j, ")"):
                if toks[j].kind == "name":
                    locals_.add(toks[j].value)
                j += 1
        if t.kind == "keyword" and t.value == "for":
            j = i + 1
            while j < n and toks[j].kind == "name":
                locals_.add(toks[j].value)
                j += 2 if op(j + 1, ",") else n
            continue
        if t.kind == "keyword" and t.value == "local":
            j = i + 1
            if j < n and toks[j].kind == "keyword" and toks[j].value == "function":
                j += 1
            while j < n and toks[j].kind == "name":
                locals_.add(toks[j].value)
                if op(j + 1, ","):
                    j += 2
                else:
                    break
            continue
        if t.kind != "name" or op(i - 1, ".") or op(i - 1, ":") or depth > 0:
            continue
        prev = toks[i - 1] if i > 0 else None
        if prev is not None and prev.kind == "keyword" and prev.value == "local":
            continue
        chain = [t.value]
        j = i
        while op(j + 1, ".") and j + 2 < n and toks[j + 2].kind == "name":
            chain.append(toks[j + 2].value)
            j += 2
        is_func_decl = prev is not None and prev.kind == "keyword" and prev.value == "function"
        if (is_func_decl or op(j + 1, "=")) and chain[0] not in locals_:
            names.add(".".join(chain))
    return sorted(names)


def toc_conditions(toc_text: str) -> Dict[str, str]:
    """{file path (posix): '[AllowLoadGameType x]...'} from a Blizzard TOC."""
    out: Dict[str, str] = {}
    for line in toc_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _TOC_LINE_RE.match(line)
        if m:
            out[m.group(1).strip().replace("\\", "/")] = m.group(2).strip()
    return out


def _source_build(source: Union[Mirror, DirSource], build: Optional[Build]) -> Build:
    if isinstance(source, DirSource):
        return source.describe()
    assert build is not None
    return build


def load_snapshot(source: Union[Mirror, DirSource], build: Optional[Build] = None,
                  cache_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read and parse what patchwatch needs from one build.

    For git sources the parsed snapshot is cached as JSON under
    ``cache_dir/snapshots/<commit>.json``.
    """
    b = _source_build(source, build)
    cache_file = None
    if isinstance(source, Mirror) and cache_dir is not None:
        cache_file = Path(cache_dir) / "snapshots" / f"{b.commit}.json.gz"
        if cache_file.is_file():
            try:
                with gzip.open(cache_file, "rt", encoding="utf-8") as fh:
                    data = json.load(fh)
                os.utime(cache_file)  # mark as recently used for prune_snapshots()
                if data.get("patchwatch_version") == __version__ and data.get("format") == SNAPSHOT_FORMAT:
                    data["build"] = b.to_json()
                    return data
            except (OSError, ValueError):
                pass

    def read(prefix: str, suffixes=(".lua",)) -> Dict[str, str]:
        if isinstance(source, Mirror):
            return source.read_dir(b.commit, prefix, suffixes)
        return source.read_dir(prefix, suffixes)

    docs = read(DOC_DIR)
    model = build_model(docs)

    dep_files = read(DEPRECATED_DIR, (".lua", ".toc"))
    dep_toc = next((t for p, t in dep_files.items() if p.lower().endswith(".toc")), "")
    conds = toc_conditions(dep_toc)
    deprecated = {}
    for p, text in dep_files.items():
        if not p.lower().endswith(".lua"):
            continue
        deprecated[p] = {
            "names": shim_names(text),
            "guarded_by_cvar": "loadDeprecationFallbacks" in text,
            "toc_condition": conds.get(p, None) if dep_toc else None,
            "in_toc": (p in conds) if dep_toc else None,
        }

    const_files = read(CONSTANTS_DIR, (".lua", ".toc"))
    ctoc = next((t for p, t in const_files.items() if p.lower().endswith(".toc")), "")
    cconds = toc_conditions(ctoc)
    constants: Dict[str, Dict[str, Any]] = {}
    for p, text in sorted(const_files.items()):
        if not p.lower().endswith(".lua"):
            continue
        for name, value in _CONST_RE.findall(text):
            constants.setdefault(name, []).append({"file": p, "value": value.strip(),
                                                   "toc_condition": cconds.get(p, "")})

    snap = {
        "patchwatch_version": __version__,
        "format": SNAPSHOT_FORMAT,
        "build": b.to_json(),
        "api_counts": summarize_model(model),
        "api": model,
        "deprecated": deprecated,
        "project_constants": constants,
        "has_docs": bool(docs),
    }
    if cache_file is not None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_file.with_name(cache_file.name + ".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                json.dump(snap, fh)
            os.replace(tmp, cache_file)
        except OSError:
            pass
    return snap


def prune_snapshots(cache_dir: Path, keep_commits: Iterable[str], keep_recent: int = 12) -> int:
    """Delete cached snapshots except those for ``keep_commits`` and the most recently used ones."""
    d = Path(cache_dir) / "snapshots"
    if not d.is_dir():
        return 0
    keep = set(keep_commits)
    files = sorted(d.glob("*.json*"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for i, f in enumerate(files):
        commit = f.name.split(".", 1)[0]
        if commit in keep or (i < keep_recent and f.name.endswith(".json.gz")):
            continue
        try:
            f.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def compare_snapshots(old: Mapping[str, Any], new: Mapping[str, Any], include_docs: bool = False) -> Dict[str, Any]:
    api = diff_models(old["api"], new["api"], include_docs=include_docs)

    od, nd = old.get("deprecated", {}), new.get("deprecated", {})
    dep = {
        "added": sorted(set(nd) - set(od)),
        "removed": sorted(set(od) - set(nd)),
        "names_added": {p: nd[p]["names"] for p in sorted(set(nd) - set(od))},
        "names_removed": {p: od[p]["names"] for p in sorted(set(od) - set(nd))},
        "changed": {},
    }
    for p in sorted(set(od) & set(nd)):
        a, b = set(od[p]["names"]), set(nd[p]["names"])
        if a != b or od[p].get("toc_condition") != nd[p].get("toc_condition"):
            dep["changed"][p] = {"names_added": sorted(b - a), "names_removed": sorted(a - b),
                                 "old_condition": od[p].get("toc_condition"),
                                 "new_condition": nd[p].get("toc_condition")}

    oc, nc = old.get("project_constants", {}), new.get("project_constants", {})
    consts = {
        "added": {k: nc[k] for k in sorted(set(nc) - set(oc))},
        "removed": {k: oc[k] for k in sorted(set(oc) - set(nc))},
        "changed": {k: {"old": oc[k], "new": nc[k]} for k in sorted(set(oc) & set(nc)) if oc[k] != nc[k]},
    }

    ob, nb = old["build"], new["build"]
    return {
        "old": ob,
        "new": nb,
        "interface": {"old": ob.get("interface"), "new": nb.get("interface"),
                      "changed": ob.get("interface") != nb.get("interface")},
        "api_counts": {"old": old.get("api_counts"), "new": new.get("api_counts")},
        "api": api,
        "deprecated": dep,
        "project_constants": consts,
        "warnings": ([] if old.get("has_docs") else ["old build has no Blizzard_APIDocumentationGenerated folder"])
        + ([] if new.get("has_docs") else ["new build has no Blizzard_APIDocumentationGenerated folder"]),
    }


def deprecated_names(snap: Mapping[str, Any]) -> Dict[str, str]:
    """{shimmed name: deprecated file} for a snapshot."""
    out: Dict[str, str] = {}
    for p, info in snap.get("deprecated", {}).items():
        for n in info["names"]:
            out.setdefault(n, p)
    return out


__all__ = ["load_snapshot", "compare_snapshots", "deprecated_names", "interface_number"]
