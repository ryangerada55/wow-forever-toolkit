"""Command-line interface.

Exit codes: 0 = success, 1 = error, 2 = bad command line (argparse),
3 = the --fail-on condition was met, 4 = the --fail-on-alert condition was met (check).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from . import __version__
from .alerts import (ALERTS_MARKER, EXPORT_WORKFLOW, EXPORTER_BRANCH, EXPORTER_FILE, Alert, age_days, band_alerts,
                     branch_set_alerts, export_product_alert, exporter_alerts, missing_branch_alerts,
                     parse_export_product, parse_exporter_products, parse_stale_days, render_alerts_markdown,
                     stale_alerts)
from .apidocs import _RESTRICTION_RE
from .mirror import DEFAULT_BRANCHES, DEFAULT_URL, Build, DirSource, Mirror, MirrorError, NotEnoughBuilds, default_cache_dir
from .report import breaking_impact, render_markdown, to_json
from .scan import KnownNames, assess_impact, scan_addon
from .snapshot import compare_snapshots, deprecated_names, load_snapshot, prune_snapshots
from .state import load_state, now_utc, save_state
from .toc import addon_display_name, check_addon, find_addon_dirs, game_type_for_interface

EXIT_OK, EXIT_ERROR, EXIT_FAIL_ON, EXIT_ALERT = 0, 1, 3, 4


def _say(msg: str) -> None:
    print(msg, file=sys.stderr)


def _branches(values: Optional[Sequence[str]], default: Sequence[str]) -> List[str]:
    if not values:
        return list(default)
    out: List[str] = []
    for v in values:
        out.extend(x.strip() for x in v.split(",") if x.strip())
    return out


def _cache_dir(args: argparse.Namespace) -> Path:
    return Path(args.cache_dir).expanduser() if args.cache_dir else default_cache_dir()


def _mirror(args: argparse.Namespace) -> Mirror:
    return Mirror(_cache_dir(args) / "wow-ui-source.git", url=args.repo_url, git=args.git,
                  offline=args.offline, verbose=args.verbose)


def _spec_branch(spec: str) -> Optional[str]:
    """The branch a build spec needs in the cache (None for dir:, tag: and commit ids)."""
    if spec.startswith(("dir:", "tag:")):
        return None
    if "@" in spec:
        return spec.split("@", 1)[0]
    if re.fullmatch(r"[0-9a-f]{7,40}", spec):
        return None
    return spec


def _open_sources(args: argparse.Namespace, specs: Sequence[str]) -> Tuple[Mirror, List[Union[Tuple[DirSource, None], Tuple[Mirror, Build]]]]:
    m = _mirror(args)
    need = sorted({b for b in (_spec_branch(s) for s in specs) if b})
    if any(not s.startswith("dir:") for s in specs):
        if not args.no_fetch:
            missing = m.fetch(need, tags=any(s.startswith("tag:") for s in specs), skip_missing=True)
            if missing:
                raise MirrorError(f"branch {', '.join(missing)} is not in the mirror {m.url} "
                                  f"(list its branches with: git ls-remote --heads {m.url})")
        elif not m.exists():
            raise MirrorError(f"no cache at {m.path}; run without --no-fetch/--offline first")
    out: List[Any] = []
    for s in specs:
        if s.startswith("dir:"):
            out.append((DirSource(Path(s[4:]).expanduser()), None))
        else:
            out.append((m, m.resolve(s)))
    return m, out


def _snapshot(args: argparse.Namespace, src: Any, build: Optional[Build]) -> Dict[str, Any]:
    return load_snapshot(src, build, cache_dir=None if args.no_snapshot_cache else _cache_dir(args))


def _addon_dirs(paths: Sequence[str]) -> List[Path]:
    dirs: List[Path] = []
    for p in paths or []:
        # Absolute, so that "." reports the folder's real name (an empty name gave an empty heading).
        found = find_addon_dirs(Path(p).expanduser().resolve())
        if not found:
            _say(f"warning: no addon (folder with a .toc) found under {p}")
        dirs.extend(found)
    return dirs


def _addon_reports(addon_dirs: Sequence[Path], snaps: Sequence[Dict[str, Any]], target: Dict[str, Any],
                   cmp: Optional[Dict[str, Any]], exclude: Sequence[str], scans: Optional[Dict[str, Any]] = None,
                   max_file_bytes: int = 5_000_000) -> List[Dict[str, Any]]:
    known = None
    out = []
    iface = target["build"].get("interface")
    gt = game_type_for_interface(iface) if iface else None
    branch = target["build"].get("branch")
    new_dep = deprecated_names(target)
    for d in addon_dirs:
        key = str(d)
        if scans is not None and key in scans:
            sc = scans[key]
        else:
            if known is None:
                known = KnownNames.from_snapshots(snaps)
            sc = scan_addon(d, known, exclude=exclude, max_file_bytes=max_file_bytes)
            if scans is not None:
                scans[key] = sc
        rep: Dict[str, Any] = {"addon": addon_display_name(d), "path": str(d),
                               "scan": {k: sc[k] for k in ("files_scanned", "skipped")}}
        if iface and gt:
            rep["toc"] = check_addon(d, gt, iface, branch)
        rep["findings"] = assess_impact(sc, cmp, new_dep) if cmp else []
        rep["restricted_api_usage"] = _restricted_usage(sc, target)
        rep["references"] = {k: len(v) for k, v in sc["refs"].items()}
        out.append(rep)
    return out


def _restricted_usage(sc: Dict[str, Any], snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Referenced functions/events that carry secret-value or restriction annotations in this build."""
    res = []
    api = snap["api"]
    for q, entry in sc["refs"]["functions"].items():
        f = api["functions"].get(q)
        if not f:
            continue
        keys = sorted(k for k, v in f["attrs"].items()
                      if v and k != "SecretArguments" and _RESTRICTION_RE.search(k))
        if f["attrs"].get("SecretArguments") == "NotAllowed":
            keys.append("SecretArguments=NotAllowed")
        if keys:
            res.append({"kind": "function", "name": q, "annotations": keys, "count": entry["count"],
                        "first": entry["locations"][0] if entry["locations"] else None})
    for q, entry in sc["refs"]["events"].items():
        e = api["events"].get(q)
        if not e:
            continue
        keys = sorted(k for k, v in e["attrs"].items() if v and _RESTRICTION_RE.search(k))
        if keys:
            res.append({"kind": "event", "name": q, "annotations": keys, "count": entry["count"],
                        "first": entry["locations"][0] if entry["locations"] else None})
    return sorted(res, key=lambda r: r["name"])


def _write(path: Optional[str], text: str) -> None:
    if not path or path == "-":
        out = sys.stdout
        try:
            out.write(text)
        except UnicodeEncodeError:  # e.g. a legacy Windows console code page
            out.write(text.encode(out.encoding or "ascii", "replace").decode(out.encoding or "ascii"))
        if not text.endswith("\n"):
            out.write("\n")
        return
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _fail_on(mode: str, cmp_counts: Dict[str, int], addons: List[Dict[str, Any]]) -> bool:
    if mode == "breaking":
        return cmp_counts.get("breaking", 0) > 0 or breaking_impact(addons) > 0
    if mode == "impact":
        return breaking_impact(addons) > 0
    return False


# ---------------------------------------------------------------- commands
def cmd_fetch(args: argparse.Namespace) -> int:
    m = _mirror(args)
    branches = _branches(args.branches, DEFAULT_BRANCHES)
    missing = m.fetch(branches, tags=args.tags, skip_missing=True)
    for b in branches:
        if b in missing:
            print(f"{b:22} {'(not in mirror)':>16}")
            continue
        bl = m.builds(b) if m.has_branch(b) else []
        last = bl[-1] if bl else None
        print(f"{b:22} {last.label if last else '(no builds)':>16}  {last.date if last else ''}")
    for b in missing:
        _say(f"WARNING: {b}: branch is not in the mirror {m.url}; nothing fetched for it")
    _say(f"cache: {m.path}")
    return EXIT_OK


def cmd_builds(args: argparse.Namespace) -> int:
    m = _mirror(args)
    branches = _branches(args.branches, DEFAULT_BRANCHES)
    if not args.no_fetch:
        m.fetch(branches, skip_missing=True)
    state = load_state(Path(args.state)) if args.state else {"branches": {}}
    rows = []
    for b in branches:
        if not m.has_branch(b):
            _say(f"WARNING: {b}: branch is not in the mirror{' cache' if args.no_fetch else ''}; skipped")
            continue
        after = None
        last = state["branches"].get(b, {}).get("commit")
        if args.new_only and last:
            after = last
        bl = m.builds(b, with_files=args.files, after=after)
        if args.since:
            bl = [x for x in bl if x.date[:10] >= args.since]
        if args.limit:
            bl = bl[-args.limit:]
        seen = state["branches"].get(b, {}).get("commit")
        all_commits = [x.commit for x in m.builds(b)] if seen else []
        seen_idx = all_commits.index(seen) if seen in all_commits else -1
        for x in bl:
            d = x.to_json()
            if seen:
                d["new"] = all_commits.index(x.commit) > seen_idx
            rows.append(d)
    if args.json:
        _write(args.json, to_json(rows))
        return EXIT_OK
    hdr = f"{'branch':20} {'date (UTC)':17} {'version.build':16} {'iface':>6}"
    if args.files:
        hdr += f" {'files':>6} {'apidoc':>6}"
    print(hdr + "  commit")
    for d in rows:
        line = f"{d['branch']:20} {d['date'][:16].replace('T', ' '):17} {d['label']:16} {str(d['interface']):>6}"
        if args.files:
            line += f" {d['files_changed']:>6} {d['api_doc_files_changed']:>6}"
        line += f"  {d['commit'][:9]}"
        if d.get("new"):
            line += "  NEW"
        print(line)
    return EXIT_OK


def cmd_diff(args: argparse.Namespace) -> int:
    _, srcs = _open_sources(args, [args.old, args.new])
    (os_, ob), (ns_, nb) = srcs
    old = _snapshot(args, os_, ob)
    new = _snapshot(args, ns_, nb)
    cmp = compare_snapshots(old, new, include_docs=args.include_docs)
    addons = _addon_reports(_addon_dirs(args.addon), [old, new], new, cmp, args.exclude,
                            max_file_bytes=args.max_file_bytes)
    rep = {"tool_version": __version__, "generated_at": now_utc(), "branch": new["build"].get("branch"),
           "comparison": cmp, "addons": addons}
    if args.title:
        rep["title"] = args.title
    md = render_markdown(rep, max_chars=args.max_md_chars)
    if args.json:
        _write(args.json, to_json(rep))
    if args.md or not args.json:
        _write(args.md, md)
    c = cmp["api"]["counts"]
    _say(f"{cmp['old'].get('label')} -> {cmp['new'].get('label')}: functions +{c['functions_added']}/-"
         f"{c['functions_removed']}/~{c['functions_changed']}, events +{c['events_added']}/-{c['events_removed']}, "
         f"restriction changes {c['restriction_changes']}, breaking {c['breaking']}, "
         f"addon impact {breaking_impact(addons)}")
    return EXIT_FAIL_ON if _fail_on(args.fail_on, c, addons) else EXIT_OK


def cmd_scan(args: argparse.Namespace) -> int:
    specs = [args.build] + ([args.compare] if args.compare else [])
    _, srcs = _open_sources(args, specs)
    target = _snapshot(args, *srcs[0])
    cmp = None
    snaps = [target]
    if args.compare:
        other = _snapshot(args, *srcs[1])
        snaps.append(other)
        cmp = compare_snapshots(other, target)
    addons = _addon_reports(_addon_dirs(args.addon), snaps, target, cmp, args.exclude,
                            max_file_bytes=args.max_file_bytes)
    rep = {"tool_version": __version__, "generated_at": now_utc(), "build": target["build"],
           "compared_with": cmp["old"] if cmp else None, "addons": addons}
    if args.json:
        _write(args.json, to_json(rep))
    if args.md or not args.json:
        _write(args.md, _render_scan_md(rep))
    n = breaking_impact(addons)
    _say(f"scanned {len(addons)} addon(s) against {target['build'].get('label')}: {n} breaking item(s)")
    return EXIT_FAIL_ON if args.fail_on != "never" and n > 0 else EXIT_OK


def _render_scan_md(rep: Dict[str, Any]) -> str:
    from .report import _render_addon, _code
    b = rep["build"]
    where = " ".join(str(x) for x in (b.get("branch"), b.get("label")) if x)
    out = [f"## patchwatch scan against {where} (Interface {b.get('interface')})\n"]
    if rep.get("compared_with"):
        out.append(f"Findings list APIs the addon references that are documented in "
                   f"{rep['compared_with'].get('label')} but not (or differently) in {b.get('label')}.\n")
    for a in rep["addons"]:
        out.extend(_render_addon(a, 100))
        ru = a.get("restricted_api_usage") or []
        if ru:
            out.append(f"<details><summary>Referenced APIs with secret-value or restriction annotations "
                       f"in this build ({len(ru)})</summary>\n")
            for r in ru[:300]:
                f = r.get("first") or {}
                out.append(f"- {_code(r['name'])} ({r['kind']}): {', '.join(r['annotations'])} "
                           f"- {f.get('file')}:{f.get('line')}")
            out.append("</details>\n")
    return "\n".join(out)


def cmd_dump(args: argparse.Namespace) -> int:
    _, srcs = _open_sources(args, [args.build])
    snap = _snapshot(args, *srcs[0])
    if args.summary:
        _write(args.json, to_json({"build": snap["build"], "api_counts": snap["api_counts"],
                                   "deprecated": {p: len(v["names"]) for p, v in snap["deprecated"].items()},
                                   "project_constants": snap["project_constants"]}))
    else:
        _write(args.json, to_json(snap))
    return EXIT_OK


def _now(args: argparse.Namespace) -> datetime:
    if getattr(args, "now", None):
        dt = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _branch_head_commit(m: Mirror, branch: str) -> Optional[str]:
    out = m.git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}^{{commit}}", check=False).strip()
    return out or None


def _read_text_or_none(m: Mirror, commit: str, path: str) -> Optional[str]:
    """One small file from the mirror, or None (missing, offline, or the blob cannot be fetched)."""
    if m.offline:
        return None
    try:
        return m.read_text(commit, path)
    except MirrorError:
        return None


def cmd_check(args: argparse.Namespace) -> int:
    m = _mirror(args)
    branches = _branches(args.branches, DEFAULT_BRANCHES)
    state_path = Path(args.state).expanduser()
    state = load_state(state_path)
    now = _now(args)
    stale_default, stale_per = parse_stale_days(args.stale_days)
    mirror_state: Dict[str, Any] = state.setdefault("mirror", {})
    alerts: List[Alert] = []
    remote: Optional[List[str]] = None
    if not args.no_fetch:
        m.init()
        remote = m.remote_branches()
        missing = [b for b in branches if b not in remote]
        exporter = args.exporter_check and EXPORTER_BRANCH in remote
        fetch_list = [b for b in branches if b in remote]
        if exporter and EXPORTER_BRANCH not in fetch_list:
            fetch_list.append(EXPORTER_BRANCH)
        m.fetch(fetch_list)
    else:
        missing = [b for b in branches if not m.has_branch(b)]
        exporter = args.exporter_check and not m.offline and m.has_branch(EXPORTER_BRANCH)
    alerts += missing_branch_alerts(missing, offline=args.no_fetch)
    if remote is not None:
        alerts += branch_set_alerts(mirror_state.get("branches"), remote)
        mirror_state["branches"] = remote
    products = None
    if exporter:
        ex = _branch_head_commit(m, EXPORTER_BRANCH)
        products = parse_exporter_products(_read_text_or_none(m, ex, EXPORTER_FILE)) if ex else None
        if products is not None:
            alerts += exporter_alerts(mirror_state.get("exporter_products"), products)
            mirror_state["exporter_products"] = products
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    addon_dirs = _addon_dirs(args.addon)
    summary: Dict[str, Any] = {"tool_version": __version__, "generated_at": now_utc(),
                               "repo_url": args.repo_url, "branches": {}, "notify_branches": [],
                               "mirror": {"branches": remote, "exporter_products": products}}
    plans = []
    heads: Dict[str, Build] = {}
    for b in branches:
        if b in missing:
            summary["branches"][b] = {"status": "missing-branch"}
            continue
        allb = m.builds(b)
        if not allb:
            summary["branches"][b] = {"status": "no-builds"}
            continue
        head = allb[-1]
        heads[b] = head
        st = state["branches"].get(b)
        prev_product = (st or {}).get("export_product")
        found = parse_export_product(_read_text_or_none(m, head.commit, EXPORT_WORKFLOW))
        alerts += export_product_alert(b, prev_product, found)
        product = found if found is not None else prev_product
        base: Optional[Build] = None
        note: Optional[str] = None
        if args.since:
            spec = args.since if "@" in args.since else f"{b}@{args.since}"
            if spec.split("@", 1)[0] != b:
                spec = f"{b}@{spec.split('@', 1)[1]}"
            try:
                base = m.resolve(spec)
            except NotEnoughBuilds as exc:
                # A branch that is new to the mirror (or to this cache) has too few builds for
                # --since: record its head as the baseline instead of failing the whole run.
                note = f"--since {args.since}: {exc}; recorded the current build as the baseline"
                _say(f"{b}: {note}")
        elif st and st.get("commit"):
            try:
                base = m.commit_info(st["commit"], b)
            except MirrorError:
                _say(f"{b}: state commit {st['commit'][:9]} not found; recording the current head")
        elif args.first_run == "previous" and len(allb) > 1:
            base = allb[-2]
        age = age_days(head, now)
        extra = {"export_product": product, "head_age_days": None if age is None else round(age, 1)}
        if base is None:
            alerts += band_alerts(b, None, head)
            summary["branches"][b] = dict({"status": "baseline-recorded", "head": head.to_json()}, **extra)
            if note:
                summary["branches"][b]["note"] = note
            state["branches"][b] = _state_entry(head, product)
            if not note:
                _say(f"{b}: first run, recorded baseline {head.label}")
            continue
        if base.commit == head.commit:
            alerts += band_alerts(b, None, head)
            summary["branches"][b] = dict({"status": "no-new-build", "head": head.to_json()}, **extra)
            if st is not None and product is not None:
                st["export_product"] = product
            _say(f"{b}: no new build (still {head.label})")
            continue
        new_builds = m.builds(b, with_files=True, after=base.commit)
        alerts += band_alerts(b, base, head, new_builds)
        plans.append((b, base, head, new_builds, extra, product))
    alerts += stale_alerts(heads, now, stale_default, stale_per)

    loaded: Dict[str, Dict[str, Any]] = {}

    def snap(build: Build) -> Dict[str, Any]:
        if build.commit not in loaded:
            loaded[build.commit] = _snapshot(args, m, build)
        return loaded[build.commit]

    for b, base, head, _, _, _ in plans:
        snap(base)
        snap(head)
    scans: Dict[str, Any] = {}
    fail = False
    for b, base, head, new_builds, extra, product in plans:
        old, new = snap(base), snap(head)
        cmp = compare_snapshots(old, new, include_docs=args.include_docs)
        addons = _addon_reports(addon_dirs, list(loaded.values()), new, cmp, args.exclude, scans=scans,
                                max_file_bytes=args.max_file_bytes)
        c = cmp["api"]["counts"]
        api_changed = (any(v for k, v in c.items() if k != "breaking")
                       or cmp["deprecated"]["added"] or cmp["deprecated"]["removed"]
                       or any(cmp["project_constants"].values()) or cmp["interface"]["changed"])
        impact = breaking_impact(addons)
        notify = {"any": True, "api": bool(api_changed),
                  "breaking": c["breaking"] > 0 or impact > 0, "impact": impact > 0}[args.notify_on]
        rep = {"tool_version": __version__, "generated_at": now_utc(), "branch": b, "comparison": cmp,
               "builds": [x.to_json() for x in new_builds], "addons": addons,
               "title": f"patchwatch: {b} {head.label} (was {base.label})"}
        md = render_markdown(rep, max_chars=args.max_md_chars)
        _write(str(out_dir / f"{b}.md"), md)
        _write(str(out_dir / f"{b}.json"), to_json(rep))
        summary["branches"][b] = dict({
            "status": "new-build", "notify": notify, "old": base.to_json(), "new": head.to_json(),
            "new_builds": len(new_builds), "api_changed": bool(api_changed), "counts": c,
            "interface_changed": cmp["interface"]["changed"], "addon_breaking_items": impact,
            "report_md": f"{b}.md", "report_json": f"{b}.json",
            "issue_title": f"[patchwatch] {b}: {head.label}" + (" (Interface " + str(head.interface) + ")" if head.interface else ""),
            "marker": f"<!-- patchwatch:branch={b} -->",
        }, **extra)
        if notify:
            summary["notify_branches"].append(b)
        state["branches"][b] = _state_entry(head, product)
        _say(f"{b}: {base.label} -> {head.label}: {len(new_builds)} new build(s); breaking API changes "
             f"{c['breaking']}; addon breaking items {impact}; notify={notify}")
        if _fail_on(args.fail_on, c, addons):
            fail = True

    previous = set(state.get("alerts") or [])
    new_keys = [a.key for a in alerts if a.key not in previous]
    summary["alerts"] = [a.to_json() for a in alerts]
    summary["new_alerts"] = new_keys
    summary["alerts_md"] = "alerts.md"
    summary["alerts_marker"] = ALERTS_MARKER
    _write(str(out_dir / "alerts.md"), render_alerts_markdown(alerts, new_keys, summary["generated_at"]))
    for a in alerts:
        _say(f"WARNING: {a.message}" + (" (new)" if a.key in new_keys else ""))
    alert_exit = {"never": False, "any": bool(alerts),
                  "missing": any(a.kind == "missing-branch" for a in alerts)}[args.fail_on_alert]
    summary["fail"] = fail
    summary["fail_alert"] = alert_exit
    _write(str(out_dir / "summary.json"), to_json(summary))
    if not args.no_update_state:
        state["repo_url"] = args.repo_url
        state["alerts"] = sorted({a.key for a in alerts})
        save_state(state_path, state)
    if not args.no_snapshot_cache:
        prune_snapshots(_cache_dir(args), [v.get("commit") for v in state["branches"].values()],
                        keep_recent=2 * len(branches))
    if fail:
        return EXIT_FAIL_ON
    return EXIT_ALERT if alert_exit else EXIT_OK


def _state_entry(b: Build, export_product: Optional[str] = None) -> Dict[str, Any]:
    return {"commit": b.commit, "version": b.version, "build": b.build, "interface": b.interface,
            "date": b.date, "seen_at": now_utc(), "export_product": export_product}


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="patchwatch", description=(
        "Tell an addon team what a new WoW build changes for its addons, using the "
        "Gethe/wow-ui-source mirror of Blizzard's UI code."))
    p.add_argument("--version", action="version", version=f"patchwatch {__version__}")
    p.add_argument("--cache-dir", help="cache folder (default: per-user cache, or PATCHWATCH_CACHE_DIR)")
    p.add_argument("--repo-url", default=DEFAULT_URL, help="mirror URL (default: %(default)s)")
    p.add_argument("--git", default="git", help="git executable (default: git on PATH)")
    p.add_argument("--no-fetch", action="store_true", help="do not update branches from the network")
    p.add_argument("--offline", action="store_true", help="no network at all (implies --no-fetch)")
    p.add_argument("--no-snapshot-cache", action="store_true", help="re-parse builds instead of using cached JSON")
    p.add_argument("-v", "--verbose", action="store_true", help="print git commands")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    def addon_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--addon", action="append", default=[], metavar="DIR",
                        help="addon folder, or a folder of addons (repeatable)")
        sp.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip files matching this glob, relative to the addon (repeatable), e.g. 'Libs/*'")
        sp.add_argument("--max-file-bytes", type=int, default=5_000_000,
                        help="skip larger source files (default: %(default)s)")

    def out_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--md", metavar="FILE", help="write Markdown here ('-' = stdout; default when no --json)")
        sp.add_argument("--json", metavar="FILE", help="write JSON here ('-' = stdout)")
        sp.add_argument("--fail-on", choices=["never", "breaking", "impact"], default="never",
                        help="exit 3 on breaking API changes ('breaking') or only when they hit a scanned "
                             "addon or its TOC ('impact')")

    sp = sub.add_parser("fetch", help="create or update the mirror cache")
    sp.add_argument("--branches", action="append", help=f"comma list (default: {','.join(DEFAULT_BRANCHES)})")
    sp.add_argument("--tags", action="store_true", help="also fetch the mirror's version tags")
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("builds", help="list builds per branch")
    sp.add_argument("--branches", action="append", help="comma list (default: the seven default branches)")
    sp.add_argument("--state", help="state file; marks builds newer than the last run")
    sp.add_argument("--new-only", action="store_true", help="only builds newer than the state file")
    sp.add_argument("--files", action="store_true", help="count changed files (and API doc files) per build")
    sp.add_argument("--since", metavar="YYYY-MM-DD")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--json", metavar="FILE")
    sp.set_defaults(func=cmd_builds)

    sp = sub.add_parser("diff", help="compare two builds",
                        description="Build specs: forever, forever@first, forever@-1, live@12.1.0, "
                                    "forever@69876, live@2026-08-20, tag:12.1.0, <commit>, dir:PATH")
    sp.add_argument("old")
    sp.add_argument("new")
    sp.add_argument("--title")
    sp.add_argument("--include-docs", action="store_true", help="also report Documentation text changes")
    sp.add_argument("--max-md-chars", type=int, default=64000)
    addon_opts(sp)
    out_opts(sp)
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("scan", help="check addons against one build")
    sp.add_argument("addon_dirs", nargs="+", metavar="ADDON_DIR")
    sp.add_argument("--build", default="forever", help="build spec to check against (default: %(default)s)")
    sp.add_argument("--compare", help="also report APIs documented in this build but missing from --build")
    sp.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    sp.add_argument("--max-file-bytes", type=int, default=5_000_000)
    out_opts(sp)
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("check", help="CI mode: report new builds since the state file")
    sp.add_argument("--state", required=True, help="state file (created on first run)")
    sp.add_argument("--branches", action="append", help="comma list (default: the seven default branches)")
    sp.add_argument("--out-dir", default="patchwatch-out")
    sp.add_argument("--since", help="ignore state; compare from this spec, e.g. 'first', '-1', '2026-10-01' "
                    "(a branch with too few builds for it gets a new baseline)")
    sp.add_argument("--first-run", choices=["record", "previous"], default="record",
                    help="with no state: only record the head (default) or compare head with the previous build")
    sp.add_argument("--notify-on", choices=["any", "api", "breaking", "impact"], default="any",
                    help="which new builds count as report-worthy in summary.json (default: %(default)s)")
    sp.add_argument("--include-docs", action="store_true", help="also report Documentation text changes")
    sp.add_argument("--max-md-chars", type=int, default=64000, help="shrink Markdown to this size (GitHub issue limit)")
    sp.add_argument("--no-update-state", action="store_true", help="dry run: do not write the state file")
    addon_opts(sp)
    sp.add_argument("--fail-on", choices=["never", "breaking", "impact"], default="never")
    sp.add_argument("--stale-days", action="append", metavar="N|BRANCH=N",
                    help="warn when a branch has had no export for more than N days (repeatable; 0 = off). "
                         "Default: forever=10, other branches off")
    sp.add_argument("--fail-on-alert", choices=["never", "missing", "any"], default="never",
                    help="exit 4 when a watched branch is missing from the mirror ('missing') or on any "
                         "mirror alert ('any'). Alerts are always printed and written to alerts.md")
    sp.add_argument("--no-exporter-check", dest="exporter_check", action="store_false",
                    help="do not read the exporter's product list from the mirror's automation branch")
    sp.add_argument("--now", metavar="ISO-TIME", help="pretend it is this time (UTC) for --stale-days; for tests")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("dump", help="print the parsed API model of one build as JSON")
    sp.add_argument("build")
    sp.add_argument("--summary", action="store_true")
    sp.add_argument("--json", metavar="FILE", default="-")
    sp.set_defaults(func=cmd_dump)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.offline:
        args.no_fetch = True
    if getattr(args, "command", None) == "scan":
        args.addon = args.addon_dirs
    try:
        return args.func(args)
    except (MirrorError, ValueError, OSError) as exc:
        _say(f"patchwatch: error: {exc}")
        return EXIT_ERROR
    except KeyboardInterrupt:
        return 130
