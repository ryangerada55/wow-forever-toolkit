"""TOC parsing and Interface-number checks.

Game types and the interface ranges follow the BigWigs packager
(``release.sh`` ``toc_to_type``): 11xxx classic (Era), 16xxx forever,
20xxx bcc (TBC Anniversary), 30xxx wrath, 380xx titan, 40xxx cata,
50xxx mists, anything else retail.

Which TOC file a client loads (most specific first) follows the order the
wowless project verified on real clients (``wowless/toc.lua`` ``suffixes()``,
commits 8d03723c and 250cfb4c, 2026-10-09/13): the game type, then its alias,
then the family, then the unsuffixed TOC; ``-`` before ``_`` for each name.

* forever: ``_Camelot``, then ``_Forever`` (an alias the Forever client accepts;
  the BigWigs packager does not know it), then ``_Mainline``, then unsuffixed.
* retail: ``_Standard``, then ``_Mainline``, then unsuffixed.
* Classic flavours: their own suffix (TBC Anniversary also ``_BCC``), then
  ``_Classic``, then unsuffixed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

TOC_SUFFIXES = {
    "forever": ["Camelot", "Forever", "Mainline"],
    "retail": ["Standard", "Mainline"],
    "classic": ["Vanilla", "Classic"],
    "bcc": ["TBC", "BCC", "Classic"],
    "wrath": ["Wrath", "WOTLKC", "Classic"],
    "titan": ["Wrath", "WOTLKC", "Classic"],
    "cata": ["Cata", "Classic"],
    "mists": ["Mists", "Classic"],
}
ALL_SUFFIXES = sorted({s for v in TOC_SUFFIXES.values() for s in v})
_SUFFIX_RE = re.compile(r"^(?P<base>.+?)[-_](?P<suffix>" + "|".join(ALL_SUFFIXES) + r")$", re.I)
_INTERFACE_RE = re.compile(r"^##\s*Interface\s*:\s*(.*)$", re.I)
_TYPED_INTERFACE_RE = re.compile(r"^##\s*Interface-([A-Za-z]+)\s*:\s*(.*)$", re.I)
_LOADCOND_RE = re.compile(r"\[(Allow|Exclude)LoadGameType\s+([^\]]*)\]", re.I)
_GATE_HEADER_RE = re.compile(r"^##\s*(Allow|Exclude)LoadGameType\s*:\s*(.*)$", re.I)

# Packager game-type names accepted after "## Interface-".
_TYPE_ALIASES = {
    "retail": "retail", "mainline": "retail", "classic": "classic", "vanilla": "classic",
    "bcc": "bcc", "tbc": "bcc", "wrath": "wrath", "wotlkc": "wrath", "cata": "cata",
    "mists": "mists", "titan": "titan", "forever": "forever", "camelot": "forever",
}


def game_type_for_interface(n: int) -> str:
    s = str(n)
    if len(s) == 5:
        if s.startswith("11"):
            return "classic"
        if s.startswith("16"):
            return "forever"
        if s.startswith("20"):
            return "bcc"
        if s.startswith("380"):
            return "titan"
        if s.startswith("30"):
            return "wrath"
        if s.startswith("40"):
            return "cata"
        if s.startswith("50"):
            return "mists"
    return "retail"


def parse_interface_list(text: str) -> List[int]:
    out = []
    for part in re.split(r"[,\s]+", text.strip()):
        if part.isdigit():
            out.append(int(part))
    return out


def parse_toc(path: Path) -> Dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    stem = Path(path).stem
    m = _SUFFIX_RE.match(stem)
    base, suffix = (m.group("base"), m.group("suffix")) if m else (stem, None)
    interfaces: List[int] = []
    interface_line = None
    typed: Dict[str, List[int]] = {}
    files: List[Dict[str, Any]] = []
    gates: Dict[str, List[str]] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        mg = _GATE_HEADER_RE.match(line)
        if mg:
            gates[mg.group(1).lower()] = [t.strip().lower() for t in mg.group(2).split(",") if t.strip()]
            continue
        mi = _INTERFACE_RE.match(line)
        if mi:
            interfaces = parse_interface_list(mi.group(1))
            interface_line = lineno
            continue
        mt = _TYPED_INTERFACE_RE.match(line)
        if mt:
            gt = _TYPE_ALIASES.get(mt.group(1).lower(), mt.group(1).lower())
            typed[gt] = parse_interface_list(mt.group(2))
            continue
        if not line or line.startswith("#"):
            continue
        conds = [(a.lower(), [t.strip().lower() for t in v.split(",") if t.strip()])
                 for a, v in _LOADCOND_RE.findall(line)]
        files.append({"line": lineno, "path": _LOADCOND_RE.sub("", line).strip(), "conditions": conds})
    return {
        "path": str(path), "name": Path(path).name, "base": base,
        "suffix": suffix, "interfaces": interfaces, "interface_line": interface_line,
        "typed_interfaces": typed, "files": files, "gates": gates,
    }


def find_addon_dirs(root: Path, max_depth: int = 2) -> List[Path]:
    """Folders that contain a TOC named after the folder (or any TOC at the root)."""
    root = Path(root)
    found: List[Path] = []

    def has_toc(d: Path) -> bool:
        return any(p.suffix.lower() == ".toc" for p in d.iterdir() if p.is_file())

    if root.is_dir() and has_toc(root):
        return [root]

    def walk(d: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith("."))
        except OSError:
            return
        for c in children:
            if has_toc(c):
                found.append(c)
            else:
                walk(c, depth + 1)

    walk(root, 1)
    return found


def addon_tocs(addon_dir: Path) -> List[Dict[str, Any]]:
    tocs = []
    for p in sorted(Path(addon_dir).iterdir()):
        if p.is_file() and p.suffix.lower() == ".toc":
            tocs.append(parse_toc(p))
    return tocs


def addon_display_name(addon_dir: Path) -> str:
    """The addon's name for reports: the folder name, or the TOC base name when a checkout
    folder is named differently (``wow-addon-sample`` holding ``HelloAzeroth.toc``)."""
    d = Path(addon_dir)
    name = d.name
    try:
        bases = sorted({t["base"] for t in addon_tocs(d)})
    except OSError:
        bases = []
    if name and (not bases or name.lower() in {b.lower() for b in bases}):
        return name
    if len(bases) == 1:
        return bases[0]
    return name or str(d)


def select_toc(tocs: List[Dict[str, Any]], game_type: str, addon_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The TOC a client of ``game_type`` would load for this addon folder."""
    if not tocs:
        return None
    name = (addon_name or "").lower()
    # Only TOCs named after the folder count for the client; fall back to any base name.
    named = [t for t in tocs if t["base"].lower() == name] or tocs
    for suf in TOC_SUFFIXES.get(game_type, []):
        for t in named:
            if t["suffix"] and t["suffix"].lower() == suf.lower():
                return t
    for t in named:
        if not t["suffix"]:
            return t
    return None


def suggest_interfaces(values: List[int], target: int) -> List[int]:
    """Add ``target``; keep other flavours; keep older same-flavour values (BigWigs style)."""
    out = sorted(set(values) | {target})
    return out


def check_addon(addon_dir: Path, game_type: str, interface: int, branch: Optional[str] = None) -> Dict[str, Any]:
    addon_dir = Path(addon_dir)
    tocs = addon_tocs(addon_dir)
    sel = select_toc(tocs, game_type, addon_dir.name)
    result: Dict[str, Any] = {
        "addon": addon_display_name(addon_dir), "game_type": game_type, "interface": interface, "branch": branch,
        "selected_toc": sel["name"] if sel else None, "tocs": [], "lint": [],
    }
    if sel is None:
        result["status"] = "no-toc"
        result["message"] = (f"no TOC this {game_type} client would load (looked for "
                             + ", ".join(f"_{s}" for s in TOC_SUFFIXES.get(game_type, [])) + " and unsuffixed)")
        return result
    own = {x.lower() for x in TOC_SUFFIXES.get(game_type, [])}
    for t in tocs:
        if t is sel:
            st = _toc_status(t, game_type, interface)
        elif t["suffix"] and t["suffix"].lower() not in own:
            st = {"toc": t["name"], "interfaces": t["interfaces"], "line": t["interface_line"],
                  "status": "other-flavor", "message": f"_{t['suffix']} TOC, not loaded by {game_type} clients"}
        else:
            st = {"toc": t["name"], "interfaces": t["interfaces"], "line": t["interface_line"],
                  "status": "not-loaded", "message": f"{sel['name']} takes precedence on {game_type}"}
        st["selected"] = t is sel
        result["tocs"].append(st)
    selst = next(s for s in result["tocs"] if s["selected"])
    result["status"] = selst["status"]
    result["message"] = selst["message"]
    result["suggested_line"] = selst.get("suggested_line")
    # lint: Forever-specific load conditions, suffixes and stubs. Game-type words a client does not
    # know are ignored (wowless real-client tests, 2026-09-24): retail and the Classic clients know
    # neither "camelot" nor "forever", so only an Exclude of "standard, classic" keeps them out.
    for t in tocs:
        if t["suffix"] and t["suffix"].lower() == "forever":
            result["lint"].append(f"{t['name']}: the Forever client accepts the _Forever suffix, but the BigWigs "
                                  "packager does not (no Forever game version on uploads). Prefer _Camelot.")
        if t["interfaces"] and all(v == 0 for v in t["interfaces"]):
            result["lint"].append(f"{t['name']}: an Interface 00000 'client not supported' stub. The BigWigs packager "
                                  "reads it as a retail version and tags the CurseForge upload for retail too; "
                                  "do not ship it.")
        allow_h, excl_h = t["gates"].get("allow", []), t["gates"].get("exclude", [])
        if any(w in ("camelot", "forever") for w in allow_h) and not {"standard", "classic"} <= set(excl_h):
            result["lint"].append(
                f"{t['name']}: '## AllowLoadGameType: {', '.join(allow_h)}' without "
                "'## ExcludeLoadGameType: standard, classic'; retail and Classic clients do not know "
                "camelot/forever and may load the addon. Add the Exclude line.")
        for f in t["files"]:
            allows = [w for a, v in f["conditions"] if a == "allow" for w in v]
            excludes = [w for a, v in f["conditions"] if a == "exclude" for w in v]
            if any(w in ("camelot", "forever") for w in allows) and not {"standard", "classic"} <= set(excludes):
                result["lint"].append(
                    f"{t['name']}:{f['line']}: [AllowLoadGameType {', '.join(allows)}] without "
                    "[ExcludeLoadGameType standard, classic]; retail and Classic clients do not know "
                    "camelot/forever and treat the condition as satisfied. Use "
                    "[AllowLoadGameType camelot][ExcludeLoadGameType standard, classic].")
    return result


def _toc_status(t: Dict[str, Any], game_type: str, interface: int) -> Dict[str, Any]:
    vals = t["interfaces"]
    same = [v for v in vals if game_type_for_interface(v) == game_type]
    st: Dict[str, Any] = {"toc": t["name"], "interfaces": vals, "line": t["interface_line"]}
    typed = t["typed_interfaces"].get(game_type)
    if typed is not None:
        st["typed_interfaces"] = typed
    if vals and all(v == 0 for v in vals):
        st["status"] = "not-supported"
        st["message"] = "Interface 0/00000: a deliberate 'client not supported' stub"
    elif interface in vals:
        st["status"] = "ok"
        st["message"] = f"declares {interface}"
    elif same and max(same) > interface:
        st["status"] = "ahead"
        st["message"] = f"declares {', '.join(map(str, same))} (newer than this build's {interface})"
    elif same:
        st["status"] = "outdated"
        st["message"] = (f"declares {', '.join(map(str, same))} for {game_type}; this build is {interface}")
        st["suggested_line"] = "## Interface: " + ", ".join(map(str, suggest_interfaces(vals, interface)))
    elif vals:
        st["status"] = "not-declared"
        st["message"] = (f"declares {', '.join(map(str, vals))} but nothing for {game_type}; "
                         f"the {game_type} client would treat it as out of date")
        st["suggested_line"] = "## Interface: " + ", ".join(map(str, suggest_interfaces(vals, interface)))
    else:
        st["status"] = "missing"
        st["message"] = "no ## Interface line"
        st["suggested_line"] = f"## Interface: {interface}"
    if typed is not None and interface not in typed:
        st.setdefault("notes", []).append(
            f"## Interface-{game_type.capitalize()} lists {', '.join(map(str, typed))}; add {interface}")
    return st
