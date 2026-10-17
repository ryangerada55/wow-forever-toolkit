"""Build a normalised API model from Blizzard_APIDocumentationGenerated and diff two models.

Model layout (all JSON-serialisable)::

    {
      "systems":    {name: {"namespace", "type", "environment", "file"}},
      "functions":  {qualified: {"system", "file", "args", "returns", "attrs"}},
      "events":     {LITERAL_NAME: {"system", "file", "name", "payload", "attrs"}},
      "tables":     {qualified: {"system", "file", "type", "fields", "attrs"}},
      "predicates": {name: {"system", "type", "attrs"}},
      "errors":     [...],
    }

Qualified names follow how addon code spells them:

* functions in a system with ``Namespace = "C_Foo"`` -> ``C_Foo.Bar``
* functions in a system without a namespace -> global ``Bar``
* functions in a ``ScriptObject`` system (widget methods) -> ``SimpleAnimAPI:SetScript``
* enumerations -> ``Enum.Name``; constants -> ``Constants.Name``; structures and
  callback types keep their bare ``Name``.
"""
from __future__ import annotations

import difflib
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .luatable import registered_tables

DOC_DIR = "Interface/AddOns/Blizzard_APIDocumentationGenerated"

# Keys that are part of an item's identity or handled separately.
_STRUCTURAL = {"Name", "Type", "Arguments", "Returns", "Payload", "Fields", "LiteralName"}
# Pure prose; ignored unless include_docs=True.
_PROSE = {"Documentation"}

# Annotation keys that describe secret-value / taint / restriction behaviour.
# Anything named after a documented predicate (Predicates = {...}) also counts.
_RESTRICTION_RE = re.compile(
    r"Secret|Restrict|Protected|Forbidden|Secure|Taint|^Requires|^Checks|"
    r"MouseFocusValid|CheckAllow|^HasRestrictions$"
)

# How permissive each SecretArguments value is (higher = more permissive).
_SECRET_ARGS_RANK = {"NotAllowed": 0, "AllowedWhenUntainted": 1, "AllowedWhenTainted": 2}
# Documentation types that are the same Lua type for callers.
_SAME_LUA_TYPE = {"string", "cstring"}
# Boolean keys where *true* means fewer restrictions.
_LOOSENING_FLAGS = {"NeverSecret", "ReturnsNeverSecret", "SecureHooksAllowed"}


# --------------------------------------------------------------------------
# model building
# --------------------------------------------------------------------------
def _norm_param(p: Any) -> Dict[str, Any]:
    if not isinstance(p, dict):
        return {"name": str(p), "attrs": {}}
    attrs = {k: v for k, v in p.items() if k != "Name"}
    return {"name": p.get("Name"), "attrs": attrs}


def _attrs(item: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in item.items() if k not in _STRUCTURAL}


def _as_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        # mixed/positional tables come back as dicts with int keys
        return [v[k] for k in sorted(k for k in v if isinstance(k, int))]
    return []


def build_model(files: Mapping[str, str]) -> Dict[str, Any]:
    """Build the API model from ``{filename: lua_source}``."""
    model: Dict[str, Any] = {
        "systems": {}, "functions": {}, "events": {}, "tables": {},
        "predicates": {}, "errors": [], "duplicates": [],
    }
    for fname in sorted(files):
        if not fname.lower().endswith(".lua"):
            continue
        tables, errors = registered_tables(files[fname])
        model["errors"].extend(f"{fname}: {e}" for e in errors)
        for sysdef in tables:
            _add_system(model, fname, sysdef)
    return model


def _put(model: Dict[str, Any], section: str, key: str, value: Dict[str, Any]) -> None:
    bucket = model[section]
    if key in bucket:
        if bucket[key] != value:
            model["duplicates"].append(f"{section}:{key} ({bucket[key].get('file')} / {value.get('file')})")
        return
    bucket[key] = value


def _add_system(model: Dict[str, Any], fname: str, sysdef: Mapping[str, Any]) -> None:
    sysname = sysdef.get("Name") or fname.rsplit("/", 1)[-1].replace("Documentation.lua", "")
    namespace = sysdef.get("Namespace")
    systype = sysdef.get("Type")
    if sysdef.get("Name"):
        model["systems"].setdefault(sysname, {
            "namespace": namespace, "type": systype,
            "environment": sysdef.get("Environment"), "file": fname,
        })
    for fn in _as_list(sysdef.get("Functions")):
        if not isinstance(fn, dict) or not fn.get("Name"):
            continue
        if systype == "ScriptObject":
            q = f"{sysname}:{fn['Name']}"
        elif namespace:
            q = f"{namespace}.{fn['Name']}"
        else:
            q = fn["Name"]
        _put(model, "functions", q, {
            "system": sysname, "file": fname,
            "args": [_norm_param(a) for a in _as_list(fn.get("Arguments"))],
            "returns": [_norm_param(r) for r in _as_list(fn.get("Returns"))],
            "attrs": _attrs(fn),
        })
    for ev in _as_list(sysdef.get("Events")):
        if not isinstance(ev, dict):
            continue
        lit = ev.get("LiteralName") or ev.get("Name")
        if not lit:
            continue
        _put(model, "events", lit, {
            "system": sysname, "file": fname, "name": ev.get("Name"),
            "payload": [_norm_param(p) for p in _as_list(ev.get("Payload"))],
            "attrs": _attrs(ev),
        })
    for tb in _as_list(sysdef.get("Tables")):
        if not isinstance(tb, dict) or not tb.get("Name"):
            continue
        ttype = tb.get("Type")
        if ttype == "Enumeration":
            q = f"Enum.{tb['Name']}"
        elif ttype == "Constants":
            q = f"Constants.{tb['Name']}"
        else:
            q = tb["Name"]
        fields = [_norm_param(f) for f in _as_list(tb.get("Fields"))]
        # Some tables document Values instead of Fields
        fields += [_norm_param(f) for f in _as_list(tb.get("Values"))]
        _put(model, "tables", q, {
            "system": sysname, "file": fname, "type": ttype,
            "fields": fields, "attrs": _attrs(tb),
        })
    for pr in _as_list(sysdef.get("Predicates")):
        if not isinstance(pr, dict) or not pr.get("Name"):
            continue
        _put(model, "predicates", pr["Name"], {
            "system": sysname, "type": pr.get("Type"), "attrs": _attrs(pr),
        })


def summarize_model(model: Mapping[str, Any]) -> Dict[str, int]:
    return {k: len(model[k]) for k in ("systems", "functions", "events", "tables", "predicates")}


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------
def _is_restriction_key(key: str, predicates: Iterable[str]) -> bool:
    return key in predicates or bool(_RESTRICTION_RE.search(key))


def _direction(key: str, old: Any, new: Any) -> str:
    """'tightened', 'loosened' or 'changed' from an addon author's view."""
    if key == "SecretArguments":
        ro, rn = _SECRET_ARGS_RANK.get(old), _SECRET_ARGS_RANK.get(new)
        if ro is not None and rn is not None:
            return "loosened" if rn > ro else "tightened"
        if old is None and rn is not None:
            return "tightened" if rn < 2 else "changed"
        return "changed"
    if key == "FailureMode":
        return "changed"
    truthy_old = bool(old) and old is not None
    truthy_new = bool(new) and new is not None
    if key in _LOOSENING_FLAGS:
        if key == "SecureHooksAllowed":
            # absent means allowed; an explicit false is a restriction
            o = True if old is None else bool(old)
            n = True if new is None else bool(new)
            if o == n:
                return "changed"
            return "loosened" if n else "tightened"
        if truthy_new and not truthy_old:
            return "loosened"
        if truthy_old and not truthy_new:
            return "tightened"
        return "changed"
    if isinstance(old, (list, dict)) or isinstance(new, (list, dict)):
        lo = len(old) if isinstance(old, (list, dict)) else 0
        ln = len(new) if isinstance(new, (list, dict)) else 0
        if ln > lo:
            return "tightened"
        if ln < lo:
            return "loosened"
        return "changed"
    if truthy_new and not truthy_old:
        return "tightened"
    if truthy_old and not truthy_new:
        return "loosened"
    return "changed"


def _attr_changes(old: Mapping[str, Any], new: Mapping[str, Any], predicates: Iterable[str],
                  include_docs: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    restr: List[Dict[str, Any]] = []
    other: List[Dict[str, Any]] = []
    docs_changed = False
    for key in sorted(set(old) | set(new)):
        ov, nv = old.get(key), new.get(key)
        if ov == nv:
            continue
        if key in _PROSE:
            docs_changed = True
            if not include_docs:
                continue
        entry = {"key": key, "old": ov, "new": nv}
        if _is_restriction_key(key, predicates):
            entry["direction"] = _direction(key, ov, nv)
            restr.append(entry)
        else:
            other.append(entry)
    return restr, other, docs_changed


def _type_str(p: Mapping[str, Any]) -> str:
    a = p.get("attrs", {})
    t = str(a.get("Type", "?"))
    if a.get("InnerType"):
        t += f"<{a['InnerType']}>"
    if a.get("Mixin"):
        t += f"({a['Mixin']})"
    if a.get("Nilable"):
        t += "?"
    return t


def describe_params(params: List[Mapping[str, Any]]) -> str:
    return ", ".join(f"{p.get('name')}: {_type_str(p)}" for p in params)


def _param_changes(old: List[Dict[str, Any]], new: List[Dict[str, Any]], role: str,
                   predicates: Iterable[str], include_docs: bool) -> List[Dict[str, Any]]:
    """Compare argument / return / payload / field lists.

    role is 'args', 'returns', 'payload' or 'fields'. Each change gets a
    severity: 'breaking', 'warning' or 'info'.
    """
    changes: List[Dict[str, Any]] = []
    if role == "fields":
        # Fields are looked up by name, not position.
        on = {p["name"]: p for p in old}
        nn = {p["name"]: p for p in new}
        for name in on:
            if name not in nn:
                changes.append({"change": "removed", "name": name, "severity": "breaking",
                                "old": _type_str(on[name])})
        for name in nn:
            if name not in on:
                changes.append({"change": "added", "name": name, "severity": "info",
                                "new": _type_str(nn[name])})
        for name in on:
            if name in nn:
                changes.extend(_one_param_change(on[name], nn[name], None, role, predicates, include_docs))
        return changes
    n = max(len(old), len(new))
    for i in range(n):
        o = old[i] if i < len(old) else None
        w = new[i] if i < len(new) else None
        if o is None and w is not None:
            nilable = bool(w["attrs"].get("Nilable")) or "Default" in w["attrs"]
            if role == "args":
                sev = "info" if nilable else "breaking"
            else:
                sev = "info"
            changes.append({"change": "added", "index": i + 1, "name": w["name"],
                            "new": _type_str(w), "severity": sev})
        elif w is None and o is not None:
            if role == "args":
                sev = "warning"  # extra trailing args are ignored by Lua, but intent changed
            else:
                sev = "breaking"  # callers reading this return/payload get nil
            changes.append({"change": "removed", "index": i + 1, "name": o["name"],
                            "old": _type_str(o), "severity": sev})
        else:
            changes.extend(_one_param_change(o, w, i + 1, role, predicates, include_docs))
    return changes


def _one_param_change(o: Dict[str, Any], w: Dict[str, Any], index: Optional[int], role: str,
                      predicates: Iterable[str], include_docs: bool) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    base: Dict[str, Any] = {"name": w["name"]}
    if index is not None:
        base["index"] = index
    if o["name"] != w["name"]:
        out.append(dict(base, change="renamed", old=o["name"], new=w["name"],
                        severity="warning" if role != "fields" else "breaking"))
    oa, wa = o["attrs"], w["attrs"]
    if oa.get("Type") != wa.get("Type") or oa.get("InnerType") != wa.get("InnerType") \
            or oa.get("Mixin") != wa.get("Mixin"):
        nr = bool(_RESTRICTION_RE.search(str(wa.get("Type", ""))))
        orr = bool(_RESTRICTION_RE.search(str(oa.get("Type", ""))))
        entry = dict(base, change="type", old=_type_str(o), new=_type_str(w), severity="warning")
        if {str(oa.get("Type")), str(wa.get("Type"))} <= _SAME_LUA_TYPE and \
                oa.get("InnerType") == wa.get("InnerType") and oa.get("Mixin") == wa.get("Mixin"):
            entry["severity"] = "info"  # e.g. cstring -> string: both are Lua strings
        if nr != orr:
            # e.g. UnitToken -> UnitTokenRestrictedForAddOns
            entry["restriction"] = True
            entry["direction"] = "tightened" if nr else "loosened"
            entry["severity"] = "breaking" if nr else "info"
        out.append(entry)
    if bool(oa.get("Nilable")) != bool(wa.get("Nilable")):
        became_nilable = bool(wa.get("Nilable"))
        if role == "args":
            sev = "info" if became_nilable else "breaking"
        else:
            sev = "warning" if became_nilable else "info"
        out.append(dict(base, change="nilable", old=bool(oa.get("Nilable")),
                        new=bool(wa.get("Nilable")), severity=sev))
    skip = {"Type", "InnerType", "Mixin", "Nilable"}
    restr, other, _ = _attr_changes({k: v for k, v in oa.items() if k not in skip},
                                    {k: v for k, v in wa.items() if k not in skip},
                                    predicates, include_docs)
    for r in restr:
        out.append(dict(base, change="restriction", key=r["key"], old=r["old"], new=r["new"],
                        direction=r["direction"],
                        severity="breaking" if r["direction"] == "tightened" else "info"))
    for r in other:
        if role == "fields" and r["key"] == "EnumValue":
            out.append(dict(base, change="value", old=r["old"], new=r["new"], severity="warning"))
        else:
            out.append(dict(base, change="attr", key=r["key"], old=r["old"], new=r["new"], severity="info"))
    return out


_SEV_ORDER = {"breaking": 0, "warning": 1, "info": 2}


def _worst(sevs: Iterable[str]) -> str:
    best = "info"
    for s in sevs:
        if _SEV_ORDER.get(s, 2) < _SEV_ORDER[best]:
            best = s
    return best


def _rename_hints(removed: List[str], added: List[str]) -> Dict[str, List[str]]:
    """Suggest likely replacements for removed names (same namespace, similar name)."""
    hints: Dict[str, List[str]] = {}

    def split(q: str) -> Tuple[str, str]:
        for sep in (":", "."):
            if sep in q:
                a, b = q.rsplit(sep, 1)
                return a, b
        return "", q

    by_ns: Dict[str, List[str]] = {}
    for a in added:
        by_ns.setdefault(split(a)[0], []).append(a)
    for r in removed:
        ns, short = split(r)
        cands = by_ns.get(ns, [])
        scored = []
        for c in cands:
            cs = split(c)[1]
            ratio = difflib.SequenceMatcher(None, short.lower(), cs.lower()).ratio()
            if ratio >= 0.6 or (len(short) > 4 and (short[:-4] in cs or cs[:-4] in short)):
                scored.append((ratio, c))
        if not ns:
            # globals: only very close matches
            scored = [s for s in scored if s[0] >= 0.8]
        scored.sort(reverse=True)
        if scored:
            hints[r] = [c for _, c in scored[:3]]
    return hints


def diff_models(old: Mapping[str, Any], new: Mapping[str, Any], include_docs: bool = False) -> Dict[str, Any]:
    predicates = set(old.get("predicates", {})) | set(new.get("predicates", {}))
    result: Dict[str, Any] = {}

    # functions --------------------------------------------------------
    of, nf = old["functions"], new["functions"]
    f_added = sorted(set(nf) - set(of))
    f_removed = sorted(set(of) - set(nf))
    f_changed: Dict[str, Any] = {}
    doc_only = 0
    for q in sorted(set(of) & set(nf)):
        a, b = of[q], nf[q]
        args = _param_changes(a["args"], b["args"], "args", predicates, include_docs)
        rets = _param_changes(a["returns"], b["returns"], "returns", predicates, include_docs)
        restr, other, docs = _attr_changes(a["attrs"], b["attrs"], predicates, include_docs)
        for r in restr:
            r["severity"] = "breaking" if r["direction"] == "tightened" else "info"
        for r in other:
            r["severity"] = "warning" if r["key"] == "MayReturnNothing" and r["new"] else "info"
        if args or rets or restr or other:
            entry = {"args": args, "returns": rets, "restrictions": restr, "attrs": other,
                     "system": b["system"],
                     "old_signature": describe_params(a["args"]) + " -> " + describe_params(a["returns"]),
                     "new_signature": describe_params(b["args"]) + " -> " + describe_params(b["returns"])}
            entry["severity"] = _worst(c["severity"] for c in args + rets + restr + other)
            f_changed[q] = entry
        elif docs:
            doc_only += 1
    result["functions"] = {
        "added": f_added, "removed": f_removed, "changed": f_changed,
        "doc_only_changes": doc_only,
        "rename_hints": _rename_hints(f_removed, f_added),
    }

    # events -----------------------------------------------------------
    oe, ne = old["events"], new["events"]
    e_added = sorted(set(ne) - set(oe))
    e_removed = sorted(set(oe) - set(ne))
    e_changed: Dict[str, Any] = {}
    for q in sorted(set(oe) & set(ne)):
        a, b = oe[q], ne[q]
        pay = _param_changes(a["payload"], b["payload"], "payload", predicates, include_docs)
        restr, other, _ = _attr_changes(a["attrs"], b["attrs"], predicates, include_docs)
        for r in restr:
            r["severity"] = "breaking" if r["direction"] == "tightened" else "info"
        for r in other:
            r["severity"] = "info"
        if pay or restr or other:
            e_changed[q] = {"payload": pay, "restrictions": restr, "attrs": other,
                            "system": b["system"],
                            "severity": _worst(c["severity"] for c in pay + restr + other)}
    result["events"] = {"added": e_added, "removed": e_removed, "changed": e_changed,
                        "rename_hints": _rename_hints(e_removed, e_added)}

    # tables -----------------------------------------------------------
    ot, nt = old["tables"], new["tables"]
    t_added = sorted(set(nt) - set(ot))
    t_removed = sorted(set(ot) - set(nt))
    t_changed: Dict[str, Any] = {}
    for q in sorted(set(ot) & set(nt)):
        a, b = ot[q], nt[q]
        fields = _param_changes(a["fields"], b["fields"], "fields", predicates, include_docs)
        restr, other, _ = _attr_changes(a["attrs"], b["attrs"], predicates, include_docs)
        for r in restr:
            r["severity"] = "breaking" if r["direction"] == "tightened" else "info"
        for r in other:
            # NumValues/MaxValue move whenever an enum grows; not interesting alone
            r["severity"] = "info"
        if fields or restr or other:
            t_changed[q] = {"type": b.get("type"), "fields": fields, "restrictions": restr,
                            "attrs": other, "system": b["system"],
                            "severity": _worst(c["severity"] for c in fields + restr + other)}
    result["tables"] = {"added": t_added, "removed": t_removed, "changed": t_changed,
                        "removed_types": {q: ot[q].get("type") for q in t_removed},
                        "added_types": {q: nt[q].get("type") for q in t_added}}

    # predicates -------------------------------------------------------
    op_, np_ = old.get("predicates", {}), new.get("predicates", {})
    result["predicates"] = {
        "added": sorted(set(np_) - set(op_)),
        "removed": sorted(set(op_) - set(np_)),
    }

    # systems ----------------------------------------------------------
    os_, ns_ = old.get("systems", {}), new.get("systems", {})
    result["systems"] = {"added": sorted(set(ns_) - set(os_)), "removed": sorted(set(os_) - set(ns_))}

    result["counts"] = diff_counts(result)
    return result


def iter_restriction_changes(diff: Mapping[str, Any]):
    """Yield (kind, name, detail) for every restriction/secret annotation change."""
    for q, c in diff["functions"]["changed"].items():
        for r in c["restrictions"]:
            yield "function", q, r
        for part in ("args", "returns"):
            for r in c[part]:
                if r.get("change") == "restriction" or r.get("restriction"):
                    yield "function", q, dict(r, where=part)
    for q, c in diff["events"]["changed"].items():
        for r in c["restrictions"]:
            yield "event", q, r
        for r in c["payload"]:
            if r.get("change") == "restriction" or r.get("restriction"):
                yield "event", q, dict(r, where="payload")
    for q, c in diff["tables"]["changed"].items():
        for r in c["restrictions"]:
            yield "table", q, r
        for r in c["fields"]:
            if r.get("change") == "restriction" or r.get("restriction"):
                yield "table", q, dict(r, where="fields")


def diff_counts(d: Mapping[str, Any]) -> Dict[str, int]:
    restr = list(iter_restriction_changes(d))
    breaking = (len(d["functions"]["removed"]) + len(d["events"]["removed"]) + len(d["tables"]["removed"])
                + sum(1 for c in d["functions"]["changed"].values() if c["severity"] == "breaking")
                + sum(1 for c in d["events"]["changed"].values() if c["severity"] == "breaking")
                + sum(1 for c in d["tables"]["changed"].values() if c["severity"] == "breaking"))
    return {
        "functions_added": len(d["functions"]["added"]),
        "functions_removed": len(d["functions"]["removed"]),
        "functions_changed": len(d["functions"]["changed"]),
        "events_added": len(d["events"]["added"]),
        "events_removed": len(d["events"]["removed"]),
        "events_changed": len(d["events"]["changed"]),
        "tables_added": len(d["tables"]["added"]),
        "tables_removed": len(d["tables"]["removed"]),
        "tables_changed": len(d["tables"]["changed"]),
        "restriction_changes": len(restr),
        "restrictions_tightened": sum(1 for _, _, r in restr if r.get("direction") == "tightened"),
        "restrictions_loosened": sum(1 for _, _, r in restr if r.get("direction") == "loosened"),
        "breaking": breaking,
    }
