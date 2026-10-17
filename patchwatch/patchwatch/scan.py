"""Static scan of addon source (.lua, .xml, .toc) for referenced WoW API names,
and intersection of those references with a build comparison.

What is detected (from a Lua token stream, comments ignored):

* namespaced calls and references: ``C_Spell.GetSpellInfo``, ``C_Spell["GetSpellInfo"]``
* global API functions: ``UnitHealth(...)``, ``local GetTime = GetTime``
* enums and constants: ``Enum.PowerType.Mana``, ``Constants.PetConsts.X``,
  ``WOW_PROJECT_CAMELOT``
* events: string literals that are documented event names, e.g. arguments to
  ``RegisterEvent``/``RegisterUnitEvent``/AceEvent, or entries of event tables
* XML: ``<Script>`` and ``<On...>`` handler bodies and ``function="..."``
  attributes

* widget methods (``cd:SetCooldown(...)``), matched by method name only, so
  findings for them are capped at "warning"

Known blind spots: aliased namespaces (``local CS = C_Spell; CS.X()``),
names built at runtime, the receiver type of widget methods, and
undocumented legacy globals (the generated docs do not list every global).
"""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

from .lualex import LineIndex, Token, tokenize

_EVENT_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
_XML_SCRIPT_RE = re.compile(r"<(Script|On[A-Za-z]+)(\s[^>]*)?>(.*?)</\1\s*>", re.S)
_XML_FUNC_ATTR_RE = re.compile(r"\bfunction\s*=\s*\"([A-Za-z_][\w.]*)\"")
_LIB_RE = re.compile(r"(^|/)(libs?|libraries|externals?)(/|$)", re.I)
_REGISTER_HINT = re.compile(r"Register|Unregister|IsEventRegistered|EventRegistry|AddEvent|Event", re.I)

MAX_LOCATIONS = 25


class KnownNames:
    """API names patchwatch looks for, taken from one or more build snapshots."""

    def __init__(self) -> None:
        self.functions: Set[str] = set()      # 'C_Spell.GetSpellInfo', 'UnitHealth'
        self.globals: Set[str] = set()        # global functions and constants
        self.namespaces: Set[str] = {"Enum", "Constants"}
        self.events: Set[str] = set()
        self.tables: Set[str] = set()         # 'Enum.PowerType', 'Constants.PetConsts'
        self.methods: Set[str] = set()        # widget method names, e.g. 'SetCooldown'

    @classmethod
    def from_snapshots(cls, snaps: Iterable[Mapping[str, Any]]) -> "KnownNames":
        k = cls()
        for s in snaps:
            api = s["api"]
            for q in api["functions"]:
                if ":" in q:
                    k.methods.add(q.split(":", 1)[1])  # matched by name only (receiver type unknown)
                    continue
                k.functions.add(q)
                if "." in q:
                    k.namespaces.add(q.split(".", 1)[0])
                else:
                    k.globals.add(q)
            k.events.update(api["events"])
            k.tables.update(q for q in api["tables"] if q.startswith(("Enum.", "Constants.")))
            for p, info in s.get("deprecated", {}).items():
                for n in info["names"]:
                    if "." in n:
                        k.functions.add(n)
                        k.namespaces.add(n.split(".", 1)[0])
                    elif ":" not in n:
                        k.globals.add(n)
            k.globals.update(s.get("project_constants", {}))
        return k


def _add(refs: Dict[str, Dict[str, Any]], name: str, loc: Dict[str, Any]) -> None:
    e = refs.setdefault(name, {"count": 0, "locations": []})
    e["count"] += 1
    last = e["locations"][-1] if e["locations"] else None
    if last and last["file"] == loc["file"] and last["line"] == loc["line"]:
        return  # same line already recorded
    if len(e["locations"]) < MAX_LOCATIONS:
        e["locations"].append(loc)


def scan_lua(src: str, rel: str, known: KnownNames, out: Dict[str, Dict[str, Dict[str, Any]]],
             line_offset: int = 0, lib: bool = False) -> None:
    toks: List[Token] = list(tokenize(src))
    li = LineIndex(src)
    n = len(toks)

    def loc(t: Token, kind: str) -> Dict[str, Any]:
        return {"file": rel, "line": li.line(t.pos) + line_offset, "kind": kind, "lib": lib}

    def is_op(j: int, v: str) -> bool:
        return 0 <= j < n and toks[j].kind == "op" and toks[j].value == v

    # names declared by "local a, b, c" (not references)
    declared: Set[int] = set()
    for i, t in enumerate(toks):
        if t.kind == "keyword" and t.value == "local":
            j = i + 1
            if j < n and toks[j].kind == "keyword" and toks[j].value == "function":
                j += 1
            while j < n and toks[j].kind == "name":
                declared.add(j)
                if is_op(j + 1, ","):
                    j += 2
                else:
                    break

    for i, t in enumerate(toks):
        if t.kind == "name":
            if is_op(i - 1, ":"):
                if t.value in known.methods and (is_op(i + 1, "(") or (i + 1 < n and toks[i + 1].kind == "string")):
                    _add(out["methods"], t.value, loc(t, "method-call"))
                continue
            if is_op(i - 1, ".") or i in declared:
                continue
            chain = [t.value]
            j = i
            while True:
                if is_op(j + 1, ".") and j + 2 < n and toks[j + 2].kind == "name":
                    chain.append(toks[j + 2].value)
                    j += 2
                elif (is_op(j + 1, "[") and j + 3 < n and toks[j + 2].kind == "string"
                      and is_op(j + 3, "]")):
                    chain.append(toks[j + 2].value)
                    j += 3
                else:
                    break
            head = chain[0]
            called = is_op(j + 1, "(") or (j + 1 < n and toks[j + 1].kind == "string")
            if len(chain) >= 2 and head in known.namespaces:
                q = f"{head}.{chain[1]}"
                if head in ("Enum", "Constants"):
                    if q in known.tables:
                        _add(out["tables"], q, loc(t, "ref"))
                    if len(chain) >= 3:
                        _add(out["table_fields"], f"{q}.{chain[2]}", loc(t, "ref"))
                elif q in known.functions:
                    _add(out["functions"], q, loc(t, "call" if called and len(chain) == 2 else "ref"))
                continue
            if len(chain) == 1 and head in known.globals:
                prev = toks[i - 1] if i > 0 else None
                if prev is not None and prev.kind == "keyword" and prev.value == "function":
                    _add(out["defines"], head, loc(t, "defines"))
                    continue
                if is_op(i + 1, "=") and not is_op(i + 1, "=="):
                    _add(out["defines"], head, loc(t, "assigns"))
                    continue
                target = "functions" if head in known.functions else "constants"
                _add(out[target], head, loc(t, "call" if called else "ref"))
        elif t.kind == "string" and _EVENT_RE.match(t.value) and t.value in known.events:
            kind = "string"
            # look back a few tokens for a Register*/Unregister* call
            for j in range(i - 1, max(-1, i - 6), -1):
                tj = toks[j]
                if tj.kind == "name" and _REGISTER_HINT.search(tj.value):
                    kind = "register"
                    break
                if tj.kind == "op" and tj.value in (";", "{", "}", "="):
                    break
            _add(out["events"], t.value, loc(t, kind))


def _new_result() -> Dict[str, Dict[str, Any]]:
    return {"functions": {}, "events": {}, "tables": {}, "table_fields": {}, "constants": {}, "defines": {},
            "methods": {}}


def scan_addon(addon_dir: Path, known: KnownNames, exclude: Iterable[str] = (),
               max_file_bytes: int = 5_000_000) -> Dict[str, Any]:
    addon_dir = Path(addon_dir)
    refs = _new_result()
    scanned = 0
    skipped: List[str] = []
    excl = list(exclude)
    for p in sorted(addon_dir.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in (".lua", ".xml"):
            continue
        rel = p.relative_to(addon_dir).as_posix()
        if any(part.startswith(".") for part in Path(rel).parts):
            continue
        if any(fnmatch.fnmatch(rel, pat) for pat in excl):
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > max_file_bytes:
            skipped.append(f"{rel} ({size} bytes > --max-file-bytes)")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        lib = bool(_LIB_RE.search(rel))
        scanned += 1
        if ext == ".lua":
            scan_lua(text, rel, known, refs, lib=lib)
        else:
            li = LineIndex(text)
            for m in _XML_SCRIPT_RE.finditer(text):
                body = m.group(3)
                if "<![CDATA[" in body:
                    body = body.replace("<![CDATA[", "         ").replace("]]>", "   ")
                scan_lua(body, rel, known, refs, line_offset=li.line(m.start(3)) - 1, lib=lib)
            for m in _XML_FUNC_ATTR_RE.finditer(text):
                name = m.group(1)
                if name in known.globals or name in known.functions:
                    _add(refs["functions"], name, {"file": rel, "line": li.line(m.start()),
                                                   "kind": "xml-attr", "lib": lib})
    return {"addon": addon_dir.name, "root": str(addon_dir), "files_scanned": scanned,
            "skipped": skipped, "refs": refs}


# --------------------------------------------------------------------------
# impact
# --------------------------------------------------------------------------
def _locs(entry: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return entry["locations"]


def assess_impact(scan: Mapping[str, Any], cmp: Mapping[str, Any],
                  new_deprecated: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """Intersect an addon scan with a build comparison.

    Returns findings sorted by severity: each has ``severity``
    (breaking/warning/info), ``kind``, ``name``, ``what`` and ``locations``.
    """
    refs = scan["refs"]
    api = cmp["api"]
    new_dep = new_deprecated or {}
    findings: List[Dict[str, Any]] = []

    def add(sev: str, kind: str, name: str, what: str, entry: Mapping[str, Any], **extra: Any) -> None:
        f = {"severity": sev, "kind": kind, "name": name, "what": what,
             "count": entry["count"], "locations": _locs(entry),
             "only_in_libraries": all(l.get("lib") for l in _locs(entry))}
        f.update(extra)
        findings.append(f)

    fr = refs["functions"]
    hints = api["functions"].get("rename_hints", {})
    for q in api["functions"]["removed"]:
        if q in fr:
            if q in new_dep:
                add("warning", "function", q, f"removed from the API docs; still provided by the "
                    f"Blizzard_Deprecated shim {new_dep[q]} (only with CVar loadDeprecationFallbacks)", fr[q],
                    replacements=hints.get(q, []))
            else:
                add("breaking", "function", q, "removed", fr[q], replacements=hints.get(q, []))
    for q, c in api["functions"]["changed"].items():
        if q in fr:
            parts = []
            for r in c["restrictions"]:
                parts.append(f"{r['key']}: {_v(r['old'])} -> {_v(r['new'])} ({r['direction']})")
            for part in ("args", "returns"):
                for r in c[part]:
                    parts.append(_param_text(part, r))
            for r in c["attrs"]:
                parts.append(f"{r['key']}: {_v(r['old'])} -> {_v(r['new'])}")
            add(c["severity"], "function", q, "; ".join(parts), fr[q],
                old_signature=c.get("old_signature"), new_signature=c.get("new_signature"))
    # Widget methods (Frame:SetScript, Cooldown:SetCooldown, ...) are matched by method name only,
    # so findings are capped at "warning".
    mr = refs.get("methods", {})
    cap = {"breaking": "warning", "warning": "warning", "info": "info"}
    for q in api["functions"]["removed"]:
        if ":" in q and q.split(":", 1)[1] in mr:
            add("warning", "widget-method", q, "removed (matched by method name; check the object type)",
                mr[q.split(":", 1)[1]])
    for q, c in api["functions"]["changed"].items():
        if ":" in q and q.split(":", 1)[1] in mr:
            parts = [f"{r['key']}: {_v(r['old'])} -> {_v(r['new'])} ({r['direction']})" for r in c["restrictions"]]
            for part in ("args", "returns"):
                parts += [_param_text(part, r) for r in c[part]]
            if not c["restrictions"] and c["severity"] == "info":
                continue  # cosmetic changes on common method names are noise
            add(cap[c["severity"]], "widget-method", q,
                "; ".join(parts) + " (matched by method name; check the object type)", mr[q.split(":", 1)[1]])
    er = refs["events"]
    ehints = api["events"].get("rename_hints", {})
    for q in api["events"]["removed"]:
        if q in er:
            add("breaking", "event", q, "removed", er[q], replacements=ehints.get(q, []))
    for q, c in api["events"]["changed"].items():
        if q in er:
            parts = [f"{r['key']}: {_v(r['old'])} -> {_v(r['new'])} ({r['direction']})" for r in c["restrictions"]]
            parts += [_param_text("payload", r) for r in c["payload"]]
            parts += [f"{r['key']}: {_v(r['old'])} -> {_v(r['new'])}" for r in c["attrs"]]
            add(c["severity"], "event", q, "; ".join(parts), er[q])
    tr, tf = refs["tables"], refs["table_fields"]
    for q in api["tables"]["removed"]:
        if q in tr:
            add("breaking", "table", q, "removed", tr[q])
    for q, c in api["tables"]["changed"].items():
        for r in c["fields"]:
            key = f"{q}.{r['name']}"
            if key in tf and r["change"] in ("removed", "value", "renamed"):
                sev = "breaking" if r["change"] in ("removed", "renamed") else "warning"
                add(sev, "table-field", key, _param_text("field", r), tf[key])
    cr = refs["constants"]
    pc = cmp.get("project_constants", {})
    for k in pc.get("removed", {}):
        if k in cr:
            add("breaking", "constant", k, "no longer defined in Blizzard_ProjectConstants", cr[k])
    for k, ch in pc.get("changed", {}).items():
        if k in cr:
            add("warning", "constant", k, f"{_const_text(ch['old'])} -> {_const_text(ch['new'])}", cr[k])
    for k, v in pc.get("added", {}).items():
        if k in cr:
            if k == "WOW_PROJECT_ID":
                add("warning", "constant", k, f"now defined: {_const_text(v)}; checks such as "
                    "WOW_PROJECT_ID == WOW_PROJECT_MAINLINE take a different branch on this client", cr[k])
            else:
                add("info", "constant", k, f"now defined: {_const_text(v)}", cr[k])
    # names the addon uses that only a removed deprecated file provided
    dep = cmp.get("deprecated", {})
    for path, names in dep.get("names_removed", {}).items():
        for nme in names:
            entry = fr.get(nme) or cr.get(nme)
            if entry and nme not in new_dep:
                add("breaking", "deprecated-shim", nme, f"its shim file {path} was removed", entry)
    order = {"breaking": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 3), f["only_in_libraries"], f["kind"], f["name"]))
    return findings


def _v(x: Any) -> str:
    """Lua-flavoured value text for reports."""
    if x is None:
        return "nil"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (list, dict)):
        return json.dumps(x, separators=(",", ":"))
    return str(x)


def _const_text(v: Any) -> str:
    if isinstance(v, list):
        return "; ".join(f"{d['value']} ({d['file']}{' ' + d['toc_condition'] if d.get('toc_condition') else ''})"
                         for d in v)
    return str(v)


def _param_text(part: str, r: Mapping[str, Any]) -> str:
    idx = f"#{r['index']} " if r.get("index") else ""
    ch = r["change"]
    if ch == "added":
        return f"{part} {idx}{r['name']} added ({r.get('new')})"
    if ch == "removed":
        return f"{part} {idx}{r['name']} removed ({r.get('old')})"
    if ch == "restriction":
        return f"{part} {idx}{r['name']}: {r['key']} {_v(r['old'])} -> {_v(r['new'])} ({r['direction']})"
    if ch == "attr":
        return f"{part} {idx}{r['name']}: {r['key']} {_v(r['old'])} -> {_v(r['new'])}"
    return f"{part} {idx}{r['name']}: {ch} {_v(r.get('old'))} -> {_v(r.get('new'))}"
