"""Markdown (GitHub-issue friendly) and JSON rendering."""
from __future__ import annotations

import json
from typing import Any, Iterable, List, Mapping, Optional

from .apidocs import iter_restriction_changes

GITHUB_ISSUE_LIMIT = 65536


def marker(branch: Optional[str]) -> str:
    return f"<!-- patchwatch:branch={branch or 'manual'} -->"


def _fmt(v: Any) -> str:
    if v is None:
        return "(none)"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return json.dumps(v, separators=(",", ":"))
    return str(v)


def _code(s: Any) -> str:
    s = _fmt(s).replace("|", "\\|").replace("`", "'")
    return f"`{s}`"


def _cell(s: Any) -> str:
    return _fmt(s).replace("|", "\\|").replace("\n", " ")


def _build_cell(b: Mapping[str, Any]) -> str:
    if not b:
        return "-"
    commit = str(b.get("commit") or "")
    sha = commit[:9] if not commit.startswith("dir:") else commit
    date = (b.get("date") or "")[:16].replace("T", " ")
    return f"{b.get('label')} ({_code(sha)}{', ' + date + ' UTC' if date else ''})"


def _limit(items: List[Any], limit: Optional[int]) -> List[Any]:
    return items if limit is None else items[:limit]


def _more(items: List[Any], limit: Optional[int]) -> str:
    if limit is not None and len(items) > limit:
        return f"\n- ...and {len(items) - limit} more (see the JSON report)\n"
    return ""


def _locations(locs: List[Mapping[str, Any]], n: int = 3) -> str:
    shown = [f"{l['file']}:{l['line']}" for l in locs[:n]]
    extra = f" +{len(locs) - n}" if len(locs) > n else ""
    return ", ".join(shown) + extra


def render_comparison_md(rep: Mapping[str, Any], limit: Optional[int] = None,
                         show_added: bool = True) -> str:
    cmp = rep["comparison"]
    api = cmp["api"]
    counts = api["counts"]
    old, new = cmp["old"], cmp["new"]
    branch = rep.get("branch")
    out: List[str] = [marker(branch)]
    title = rep.get("title") or f"patchwatch: {branch or 'diff'} {old.get('label')} -> {new.get('label')}"
    out.append(f"## {title}\n")

    iface = cmp["interface"]
    ic = f"{iface['old']} -> **{iface['new']}**" if iface["changed"] else f"{iface['new']} (unchanged)"
    oc, nc = (cmp.get("api_counts") or {}).get("old") or {}, (cmp.get("api_counts") or {}).get("new") or {}
    out.append("| | Old | New |\n|---|---|---|")
    out.append(f"| Build | {_build_cell(old)} | {_build_cell(new)} |")
    out.append(f"| Interface | {iface['old']} | {iface['new']} |")
    if oc and nc:
        out.append(f"| Documented functions / events / tables | {oc.get('functions')} / {oc.get('events')} / "
                   f"{oc.get('tables')} | {nc.get('functions')} / {nc.get('events')} / {nc.get('tables')} |")
    out.append("")
    if iface["changed"]:
        out.append(f"**Interface number changed:** {ic}. Bump `## Interface` in your TOCs (see Addon impact).\n")
    for w in cmp.get("warnings", []):
        out.append(f"> Warning: {w}\n")

    builds = rep.get("builds") or []
    if builds:
        out.append("### New builds since the last run\n")
        out.append("| Date (UTC) | Build | Commit | Files changed | API doc files changed |\n|---|---|---|---|---|")
        for b in _limit(builds, limit if limit is None else max(limit, 10)):
            out.append(f"| {(b.get('date') or '')[:16].replace('T', ' ')} | {b.get('label')} | "
                       f"{_code(str(b.get('commit'))[:9])} | {_fmt(b.get('files_changed'))} | "
                       f"{_fmt(b.get('api_doc_files_changed'))} |")
        out.append("")

    out.append("### Summary\n")
    out.append(f"- Functions: +{counts['functions_added']} / -{counts['functions_removed']} / "
               f"{counts['functions_changed']} changed")
    out.append(f"- Events: +{counts['events_added']} / -{counts['events_removed']} / {counts['events_changed']} changed")
    out.append(f"- Tables (enums, structures, constants): +{counts['tables_added']} / -{counts['tables_removed']} / "
               f"{counts['tables_changed']} changed")
    out.append(f"- Restriction / secret-value annotations: {counts['restriction_changes']} changes "
               f"({counts['restrictions_tightened']} tightened, {counts['restrictions_loosened']} loosened)")
    dep = cmp["deprecated"]
    out.append(f"- Blizzard_Deprecated files: +{len(dep['added'])} / -{len(dep['removed'])}")
    pc = cmp["project_constants"]
    out.append(f"- Project constants: +{len(pc['added'])} / -{len(pc['removed'])} / {len(pc['changed'])} changed")
    out.append(f"- Breaking API changes: **{counts['breaking']}**")
    if api["functions"].get("doc_only_changes"):
        out.append(f"- Documentation-text-only changes (ignored): {api['functions']['doc_only_changes']} functions")
    out.append("")

    # ---- addon impact -------------------------------------------------
    addons = rep.get("addons") or []
    if addons:
        out.append("### Addon impact\n")
        for a in addons:
            out.extend(_render_addon(a, limit))

    # ---- breaking -----------------------------------------------------
    out.append("### Removed APIs\n")
    rm_f = api["functions"]["removed"]
    hints = api["functions"].get("rename_hints", {})
    if rm_f:
        out.append(f"**Functions ({len(rm_f)})**\n")
        for q in _limit(rm_f, limit):
            h = hints.get(q)
            out.append(f"- {_code(q)}" + (f" - possible replacement: {', '.join(_code(x) for x in h)}" if h else ""))
        out.append(_more(rm_f, limit))
    rm_e = api["events"]["removed"]
    eh = api["events"].get("rename_hints", {})
    if rm_e:
        out.append(f"**Events ({len(rm_e)})**\n")
        for q in _limit(rm_e, limit):
            h = eh.get(q)
            out.append(f"- {_code(q)}" + (f" - possible replacement: {', '.join(_code(x) for x in h)}" if h else ""))
        out.append(_more(rm_e, limit))
    rm_t = api["tables"]["removed"]
    if rm_t:
        out.append(f"**Tables ({len(rm_t)})**\n")
        for q in _limit(rm_t, limit):
            out.append(f"- {_code(q)} ({api['tables']['removed_types'].get(q)})")
        out.append(_more(rm_t, limit))
    rm_vals = [(q, r) for q, c in api["tables"]["changed"].items() for r in c["fields"]
               if r["change"] in ("removed", "renamed")]
    if rm_vals:
        out.append(f"**Enum values / structure fields removed or renamed ({len(rm_vals)})**\n")
        for q, r in _limit(rm_vals, limit):
            out.append(f"- {_code(q + '.' + str(r['name']))}: {r['change']}"
                       + (f" (was {_code(r.get('old'))})" if r.get("old") else ""))
        out.append(_more(rm_vals, limit))
    if not (rm_f or rm_e or rm_t or rm_vals):
        out.append("None.\n")

    # ---- restrictions -------------------------------------------------
    _dir_order = {"tightened": 0, "changed": 1, "loosened": 2}
    restr = sorted(iter_restriction_changes(api), key=lambda x: (_dir_order.get(x[2].get("direction"), 1), x[1]))
    out.append("### Restriction and secret-value annotation changes\n")
    if restr:
        out.append("| API | Kind | Where | Annotation | Old | New | Direction |\n|---|---|---|---|---|---|---|")
        for kind, q, r in _limit(restr, limit):
            where = r.get("where", "")
            if where and r.get("name"):
                where = f"{where} {r['name']}"
            key = r.get("key") or "Type"
            out.append(f"| {_code(q)} | {kind} | {_cell(where) or '-'} | {_cell(key)} | {_code(r.get('old'))} | "
                       f"{_code(r.get('new'))} | {r.get('direction', 'changed')} |")
        out.append(_more(restr, limit))
    else:
        out.append("None.\n")

    # ---- signature changes ------------------------------------------
    sig = [(q, c) for q, c in api["functions"]["changed"].items() if c["args"] or c["returns"]]
    out.append("### Function signature changes\n")
    if sig:
        out.append("| Function | Severity | Old | New |\n|---|---|---|---|")
        for q, c in _limit(sig, limit):
            out.append(f"| {_code(q)} | {c['severity']} | {_code(c['old_signature'])} | {_code(c['new_signature'])} |")
        out.append(_more(sig, limit))
    else:
        out.append("None.\n")
    ev = [(q, c) for q, c in api["events"]["changed"].items() if c["payload"]]
    if ev:
        out.append("### Event payload changes\n")
        for q, c in _limit(ev, limit):
            from .scan import _param_text
            out.append(f"- {_code(q)} ({c['severity']}): " + "; ".join(_param_text("payload", r) for r in c["payload"]))
        out.append(_more(ev, limit))

    # ---- deprecated & constants --------------------------------------
    if dep["added"] or dep["removed"] or dep["changed"]:
        out.append("### Blizzard_Deprecated\n")
        for p in dep["added"]:
            names = dep["names_added"].get(p, [])
            out.append(f"- added {_code(p)} ({len(names)} shimmed names)")
        for p in dep["removed"]:
            names = dep["names_removed"].get(p, [])
            out.append(f"- **removed** {_code(p)} ({len(names)} shimmed names: "
                       + ", ".join(_code(n) for n in _limit(names, 15))
                       + (" ..." if len(names) > 15 else "") + ")")
        for p, c in dep["changed"].items():
            out.append(f"- changed {_code(p)}: +{len(c['names_added'])} / -{len(c['names_removed'])} names"
                       + (f"; load condition {_code(c['old_condition'])} -> {_code(c['new_condition'])}"
                          if c["old_condition"] != c["new_condition"] else ""))
        out.append("\nShims load only when the CVar `loadDeprecationFallbacks` is enabled; do not rely on them.\n")
    if pc["added"] or pc["removed"] or pc["changed"]:
        from .scan import _const_text
        out.append("### Blizzard_ProjectConstants\n")
        for k, v in pc["added"].items():
            out.append(f"- added {_code(k)} = {_const_text(v)}")
        for k, v in pc["removed"].items():
            out.append(f"- **removed** {_code(k)} (was {_const_text(v)})")
        for k, v in pc["changed"].items():
            out.append(f"- changed {_code(k)}: {_const_text(v['old'])} -> {_const_text(v['new'])}")
        out.append("")

    # ---- added ------------------------------------------------------
    if show_added:
        for label, items in (("functions", api["functions"]["added"]), ("events", api["events"]["added"]),
                             ("tables", api["tables"]["added"])):
            if items:
                out.append(f"<details><summary>Added {label} ({len(items)})</summary>\n")
                out.extend(f"- {_code(x)}" for x in _limit(items, limit))
                out.append(_more(items, limit))
                out.append("</details>\n")
    else:
        out.append("_Lists of added APIs omitted to fit the issue size limit; see the JSON report._\n")
    other = [(q, c) for q, c in api["functions"]["changed"].items()
             if not c["args"] and not c["returns"] and not c["restrictions"]]
    if other:
        out.append(f"<details><summary>Other function attribute changes ({len(other)})</summary>\n")
        for q, c in _limit(other, limit):
            out.append(f"- {_code(q)}: " + "; ".join(f"{r['key']} {_fmt(r['old'])} -> {_fmt(r['new'])}" for r in c["attrs"]))
        out.append(_more(other, limit))
        out.append("</details>\n")

    out.append(f"\n<sub>Generated by patchwatch {rep.get('tool_version', '')} from the Gethe/wow-ui-source "
               f"mirror. The generated API docs do not list every global or widget method; treat "
               f"\"not referenced\" as a hint, not a guarantee.</sub>\n")
    return "\n".join(out)


def _render_addon(a: Mapping[str, Any], limit: Optional[int]) -> List[str]:
    out: List[str] = []
    scan = a.get("scan") or {}
    out.append(f"#### {a.get('addon')}\n")
    toc = a.get("toc")
    if toc:
        out.append(f"TOC check for {toc['game_type']} (Interface {toc['interface']}): **{toc['status']}** - "
                   f"{toc.get('message', '')}\n")
        if toc.get("tocs"):
            out.append("| TOC | Loaded by this client | Interface | Status | Suggestion |\n|---|---|---|---|---|")
            for t in toc["tocs"]:
                out.append(f"| {_code(t['toc'])} | {'yes' if t['selected'] else ''} | "
                           f"{_cell(', '.join(map(str, t['interfaces'])) or '-')} | {t['status']} | "
                           f"{_code(t['suggested_line']) if t.get('suggested_line') else ''} |")
            out.append("")
        for l in toc.get("lint", []):
            out.append(f"- Note: {l}")
        if toc.get("lint"):
            out.append("")
    findings = a.get("findings") or []
    if scan:
        out.append(f"Scanned {scan.get('files_scanned', 0)} files"
                   + (f" ({len(scan.get('skipped', []))} skipped)" if scan.get("skipped") else "") + ".")
    if not findings:
        out.append("No referenced API is affected by this build.\n")
        return out
    nb = sum(1 for f in findings if f["severity"] == "breaking")
    nw = sum(1 for f in findings if f["severity"] == "warning")
    out.append(f"**{nb} breaking, {nw} warnings, {len(findings) - nb - nw} info** for APIs this addon references.\n")
    out.append("| Severity | Kind | Name | Change | Where |\n|---|---|---|---|---|")
    for f in _limit(findings, limit):
        what = f["what"]
        if f.get("replacements"):
            what += " - possible replacement: " + ", ".join(f["replacements"])
        where = _locations(f["locations"]) + (" (libraries only)" if f.get("only_in_libraries") else "")
        out.append(f"| {f['severity']} | {f['kind']} | {_code(f['name'])} | {_cell(what)} | {_cell(where)} |")
    out.append(_more(findings, limit))
    return out


def render_markdown(rep: Mapping[str, Any], max_chars: int = GITHUB_ISSUE_LIMIT - 1536) -> str:
    """Render, shrinking long lists until the text fits ``max_chars`` (GitHub issue limit)."""
    for limit, added in ((None, True), (200, True), (100, True), (50, False), (20, False), (5, False)):
        md = render_comparison_md(rep, limit=limit, show_added=added)
        if len(md) <= max_chars:
            return md
    return md[:max_chars - 200] + "\n\n_(truncated; see the JSON report)_\n"


def to_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=False, default=str, ensure_ascii=False)


def breaking_impact(addons: Iterable[Mapping[str, Any]]) -> int:
    n = 0
    for a in addons:
        n += sum(1 for f in a.get("findings") or [] if f["severity"] == "breaking")
        toc = a.get("toc") or {}
        if toc.get("status") in ("outdated", "not-declared", "missing", "no-toc"):
            n += 1
    return n
