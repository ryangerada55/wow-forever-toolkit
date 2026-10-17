"""Mirror health alerts for ``patchwatch check``.

A clean "no new build" report is only trustworthy while the mirror still exports the product you
care about. These checks catch the ways it can go blind without failing:

* a watched branch is missing from the mirror (renamed, deleted, or never existed);
* a watched branch has had no export for N days (``--stale-days``; on by default for ``forever``);
* the ``forever`` branch carries a version outside WoW: Forever's 1.6x band (the beta product was
  reused for another game), or any branch's version band changes (another game on that product);
* mirror branches appear or disappear, the exporter's product list (``automation`` branch,
  ``ExportInterfaceFiles.ps1``) changes, or a branch's export workflow switches product.

Each alert has a stable ``key``; ``check`` stores the keys of the current alerts in the state
file, so CI can notify only when an alert is new.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .mirror import Build

# Built-in staleness thresholds in days; 0 = off. Observed export gaps on the mirror over the year
# to 2026-10-16: forever at most 4 days (beta), live 22, ptr 44, classic_era 84.
DEFAULT_STALE_DAYS: Dict[str, int] = {"forever": 10}
DEFAULT_STALE_DAYS_OTHER = 0

EXPORTER_FILE = "ExportInterfaceFiles.ps1"
EXPORTER_BRANCH = "automation"
EXPORT_WORKFLOW = ".github/workflows/export.yml"

_EXPORTER_SET_RE = re.compile(r"\[ValidateSet\(([^)]*)\)\]\s*\[string\]\s*\$Product\b", re.I)
_EXPORT_PRODUCT_RE = re.compile(r"^\s*product:\s*[\"']?([A-Za-z0-9_.-]+)", re.M)
_VERSION_RE = re.compile(r"^\s*(\d+)\.(\d+)")


@dataclass
class Alert:
    kind: str
    key: str
    message: str
    branch: Optional[str] = None
    hint: str = ""

    def to_json(self) -> Dict[str, object]:
        return asdict(self)


# ---------------------------------------------------------------- versions
def version_band(version: Optional[str]) -> Optional[str]:
    """The game a version number belongs to: 'retail', 'forever', 'classic-era', 'tbc', ..."""
    m = _VERSION_RE.match(version or "")
    if not m:
        return None
    major, minor = int(m.group(1)), int(m.group(2))
    if major >= 10:
        return "retail"
    if major == 1:
        return "forever" if minor >= 60 else "classic-era"
    if major == 3 and minor >= 80:
        return "titan"
    return {2: "tbc", 3: "wrath", 4: "cata", 5: "mists"}.get(major, f"classic-{major}")


def is_forever_16x(version: Optional[str]) -> bool:
    """1.60 to 1.69: the band the BigWigs packager maps to Forever (interface 16xxx)."""
    m = _VERSION_RE.match(version or "")
    return bool(m) and int(m.group(1)) == 1 and 60 <= int(m.group(2)) <= 69


def band_alerts(branch: str, base: Optional[Build], head: Build, new_builds: Sequence[Build] = ()) -> List[Alert]:
    """Forever's 1.6x guard (every run) and a version-band change since ``base``."""
    alerts: List[Alert] = []
    if branch == "forever":
        off = [b for b in list(new_builds) + [head] if b.version and not is_forever_16x(b.version)]
        if off:
            b = off[-1]
            band = version_band(b.version)
            if band == "forever":
                what = (f"{b.label} is WoW: Forever but no longer 1.6x; the BigWigs packager maps only "
                        "interface 16xxx to Forever, so check TOCs and upload game versions")
            else:
                what = (f"{b.label} is not a WoW: Forever build ({band}): the beta product was probably "
                        "reused for another game, and Forever builds no longer reach this branch")
            alerts.append(Alert("version-band", f"forever-band:{band}", f"forever: newest build {what}.",
                                branch, "PATCH_DAY.md, 'Launch day': find the branch that carries Forever now."))
    if base is not None and base.version and head.version:
        old, new = version_band(base.version), version_band(head.version)
        if old and new and old != new:
            alerts.append(Alert(
                "version-band", f"band-change:{branch}:{old}->{new}",
                f"{branch}: version band changed from {old} ({base.label}) to {new} ({head.label}); "
                "the product behind this branch now carries another game.", branch,
                "Check which mirror branch carries the game you ship for, and fix --branches."))
    return alerts


# ---------------------------------------------------------------- staleness
def parse_stale_days(values: Optional[Sequence[str]]) -> Tuple[Optional[int], Dict[str, int]]:
    """'--stale-days 14' (every branch) and '--stale-days forever=7' (one branch); 0 = off."""
    default: Optional[int] = None
    per: Dict[str, int] = {}
    for raw in values or []:
        for part in re.split(r"[,\s]+", raw.strip()):
            if not part:
                continue
            name, sep, num = part.partition("=")
            if not sep:
                name, num = "", part
            if not num.isdigit():
                raise ValueError(f"--stale-days: expected N or BRANCH=N (whole days), got {part!r}")
            if name:
                per[name] = int(num)
            else:
                default = int(num)
    return default, per


def stale_threshold(branch: str, cli_default: Optional[int], cli_per: Dict[str, int]) -> int:
    if branch in cli_per:
        return cli_per[branch]
    if cli_default is not None:
        return cli_default
    return DEFAULT_STALE_DAYS.get(branch, DEFAULT_STALE_DAYS_OTHER)


def _parse_utc(iso: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def age_days(build: Build, now: datetime) -> Optional[float]:
    dt = _parse_utc(build.date or "")
    return None if dt is None else (now - dt).total_seconds() / 86400.0


def stale_alerts(heads: Dict[str, Build], now: datetime, cli_default: Optional[int] = None,
                 cli_per: Optional[Dict[str, int]] = None) -> List[Alert]:
    """A watched branch whose newest export is older than its threshold."""
    alerts: List[Alert] = []
    ages = {b: age_days(h, now) for b, h in heads.items()}
    for b, h in heads.items():
        limit = stale_threshold(b, cli_default, cli_per or {})
        age = ages[b]
        if limit <= 0 or age is None or age <= limit:
            continue
        fresher = sorted(((a, o) for o, a in ages.items() if o != b and a is not None and a < age),
                         key=lambda t: t[0])
        if fresher:
            a, o = fresher[0]
            ctx = f" Meanwhile {o} exported {heads[o].label} on {heads[o].date[:10]}."
        else:
            ctx = " No other watched branch exported more recently either."
        hint = ("For forever: check whether WoW: Forever moved to another product (PATCH_DAY.md, 'Launch "
                "day') and add its mirror branch to the watched branches once it exists."
                if b == "forever" else "The mirror exports on demand; check the game launcher.")
        alerts.append(Alert("stale-branch", f"stale:{b}",
                            f"{b}: no new export for {age:.1f} days (newest {h.label} from {h.date[:10]}; "
                            f"limit {limit} days).{ctx}", b, hint))
    return alerts


# ---------------------------------------------------------------- branches
def missing_branch_alerts(missing: Sequence[str], offline: bool) -> List[Alert]:
    where = "the local cache (run without --no-fetch/--offline)" if offline else "the mirror"
    return [Alert("missing-branch", f"missing:{b}",
                  f"{b}: branch is not in {where}. patchwatch cannot see its builds.", b,
                  "Renamed or removed upstream? Compare with 'git ls-remote --heads <mirror>' and fix --branches.")
            for b in missing]


def branch_set_alerts(previous: Optional[Sequence[str]], current: Sequence[str]) -> List[Alert]:
    """New or removed mirror branches since the last run (nothing on the first run)."""
    if previous is None:
        return []
    prev, cur = set(previous), set(current)
    alerts = [Alert("new-branch", f"new-branch:{b}",
                    f"The mirror has a new branch: {b}.", b,
                    "A new product or game? If it carries WoW: Forever, add it to the watched branches.")
              for b in sorted(cur - prev)]
    alerts += [Alert("removed-branch", f"removed-branch:{b}",
                     f"The mirror no longer has the branch {b}.", b,
                     "If you watch it, patchwatch now reports it as missing.")
               for b in sorted(prev - cur)]
    return alerts


# ---------------------------------------------------------------- exporter
def parse_exporter_products(text: Optional[str]) -> Optional[List[str]]:
    """Products the mirror's exporter accepts: the ValidateSet on its $Product parameter."""
    m = _EXPORTER_SET_RE.search(text or "")
    if not m:
        return None
    return sorted(set(re.findall(r"[\"']([^\"']+)[\"']", m.group(1))))


def parse_export_product(text: Optional[str]) -> Optional[str]:
    """The product a branch's own export workflow exports (``product:`` in export.yml)."""
    m = _EXPORT_PRODUCT_RE.search(text or "")
    return m.group(1) if m else None


def exporter_alerts(previous: Optional[Sequence[str]], current: Optional[Sequence[str]]) -> List[Alert]:
    if previous is None or current is None:
        return []
    added, removed = sorted(set(current) - set(previous)), sorted(set(previous) - set(current))
    alerts = []
    if added:
        alerts.append(Alert("exporter-products", "exporter-added:" + ",".join(added),
                            f"The mirror's exporter now accepts the product(s) {', '.join(added)} "
                            f"({EXPORTER_BRANCH}:{EXPORTER_FILE}).", None,
                            "A branch for it usually follows; watch for a new-branch alert."))
    if removed:
        alerts.append(Alert("exporter-products", "exporter-removed:" + ",".join(removed),
                            f"The mirror's exporter no longer accepts the product(s) {', '.join(removed)}.",
                            None, "Branches that exported them will stop getting builds."))
    return alerts


def export_product_alert(branch: str, previous: Optional[str], current: Optional[str]) -> List[Alert]:
    if not previous or not current or previous == current:
        return []
    return [Alert("export-product", f"export-product:{branch}:{current}",
                  f"{branch}: the branch now exports product {current} (was {previous}).", branch,
                  "For forever this is the launch switch: re-check the folder and TOCs (PATCH_DAY.md).")]


# ---------------------------------------------------------------- output
ALERTS_MARKER = "<!-- patchwatch:alerts -->"


def render_alerts_markdown(alerts: Sequence[Alert], new_keys: Sequence[str], generated_at: str) -> str:
    out = [ALERTS_MARKER, f"## patchwatch: mirror alerts ({generated_at})", ""]
    if not alerts:
        out.append("No alerts: every watched branch exists and is current.")
        return "\n".join(out) + "\n"
    new = set(new_keys)
    for a in alerts:
        flag = " **(new)**" if a.key in new else ""
        out.append(f"- {a.message}{flag}")
        if a.hint:
            out.append(f"  - {a.hint}")
    out.append("")
    out.append("Alerts repeat on every run until the cause goes away; an issue comment is added only "
               "when a new one appears.")
    return "\n".join(out) + "\n"
