"""Mirror health alerts: missing, stale and re-purposed branches, new or removed mirror branches,
the exporter's product list and a branch's export product."""
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

import pytest
from conftest import git, make_tree

from patchwatch import cli
from patchwatch.alerts import (band_alerts, branch_set_alerts, export_product_alert, exporter_alerts,
                               is_forever_16x, parse_export_product, parse_exporter_products, parse_stale_days,
                               stale_alerts, stale_threshold, version_band)
from patchwatch.mirror import Build

# The two lines of the mirror's ExportInterfaceFiles.ps1 (automation branch, ab11156e) that matter.
EXPORTER_PS1 = '''param (
    [Parameter(Mandatory)]
    [ValidateSet("wow", "wow_anniversary", "wow_classic", "wow_classic_beta", "wow_classic_era", "wowt")]
    [string] $Product,

    [Parameter()]
    [ValidateSet("us", "eu", "kr", "cn")]
    [string] $Region = "us"
)
function Get-Thing {
    param (
        [Parameter(Mandatory)]
        [ValidateSet("wow", "wowz")]
        [string] $Product
    )
}
'''
EXPORT_YML = """name: Extract interface files from CDN
on:
  workflow_dispatch:
jobs:
  build:
    steps:
      - name: Export UI source files
        uses: Gethe/wow-ui-source@automation
        with:
          product: {product}
          token: ${{{{ secrets.GITHUB_TOKEN }}}}
"""


def run_cli(*args):
    return cli.main([str(a) for a in args])


def _env(date):
    return dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
                GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)


def commit_build(repo, which, version, build, date, extra=None):
    """Like conftest.commit_tree, plus extra files {path: text} in the same commit."""
    for p in repo.iterdir():
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    tmp = repo.parent / f"_tree_{which}_{build}"
    make_tree(tmp, which, f"{version}.{build}")
    for p in tmp.iterdir():
        shutil.move(str(p), str(repo / p.name))
    shutil.rmtree(tmp)
    for rel, text in (extra or {}).items():
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    subprocess.run(["git", "commit", "-q", "-m", f"{version} ({build})"], cwd=repo, check=True, env=_env(date))
    return git(repo, "rev-parse", "HEAD").strip()


def commit_file(repo, branch, rel, text, subject, date):
    git(repo, "checkout", "-q", branch)
    f = repo / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    subprocess.run(["git", "commit", "-q", "-m", subject], cwd=repo, check=True, env=_env(date))


def summary(out):
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


def kinds(s):
    return sorted(a["key"] for a in s["alerts"])


# ------------------------------------------------------------------ unit tests
@pytest.mark.parametrize("version,band", [
    ("1.60.1", "forever"), ("1.69.0", "forever"), ("1.70.0", "forever"), ("1.15.9", "classic-era"),
    ("2.5.6", "tbc"), ("3.4.5", "wrath"), ("3.80.2", "titan"), ("4.4.2", "cata"), ("5.5.4", "mists"),
    ("12.1.5", "retail"), ("13.0.0", "retail"), (None, None), ("x", None),
])
def test_version_band(version, band):
    assert version_band(version) == band


def test_forever_16x_band():
    assert is_forever_16x("1.60.1") and is_forever_16x("1.69.9")
    assert not is_forever_16x("1.70.0") and not is_forever_16x("2.5.7") and not is_forever_16x("12.1.7")


def test_band_alerts():
    b = lambda v, n: Build("x", f"c{n}", "2026-10-01T00:00:00Z", v, n)  # noqa: E731
    assert band_alerts("forever", None, b("1.60.1", 1)) == []
    # the beta slot reused for another game
    a = band_alerts("forever", b("1.60.1", 1), b("2.5.7", 2), [b("2.5.7", 2)])
    assert [x.key for x in a] == ["forever-band:tbc", "band-change:forever:forever->tbc"]
    assert "not a WoW: Forever build" in a[0].message
    # still Forever, but outside the packager's 16xxx mapping
    a = band_alerts("forever", None, b("1.70.0", 3))
    assert [x.key for x in a] == ["forever-band:forever"] and "16xxx" in a[0].message
    # an intermediate build outside the band is caught even if the head is back in it
    a = band_alerts("forever", b("1.60.1", 1), b("1.60.1", 3), [b("5.5.0", 2), b("1.60.1", 3)])
    assert [x.key for x in a] == ["forever-band:mists"]
    # another branch: only a change of band counts
    assert band_alerts("live", b("12.1.5", 1), b("12.1.7", 2)) == []
    assert band_alerts("live", b("12.1.7", 1), b("13.0.0", 2)) == []
    a = band_alerts("classic_era_ptr", b("1.15.8", 1), b("2.5.6", 2))
    assert [x.key for x in a] == ["band-change:classic_era_ptr:classic-era->tbc"]


def test_parse_stale_days():
    assert parse_stale_days(None) == (None, {})
    assert parse_stale_days(["14", "forever=7,live=30"]) == (14, {"forever": 7, "live": 30})
    with pytest.raises(ValueError):
        parse_stale_days(["forever=soon"])
    # precedence: per-branch CLI > global CLI > built-in (forever=10, others off)
    assert stale_threshold("forever", None, {}) == 10 and stale_threshold("live", None, {}) == 0
    assert stale_threshold("forever", 30, {}) == 30 and stale_threshold("live", 30, {}) == 30
    assert stale_threshold("forever", 30, {"forever": 0}) == 0


def test_stale_alerts_context():
    now = datetime(2026, 10, 30, tzinfo=timezone.utc)
    heads = {"forever": Build("forever", "a", "2026-10-16T00:52:28Z", "1.60.1", 70425),
             "live": Build("live", "b", "2026-10-28T21:16:13Z", "12.1.5", 70500),
             "ptr": Build("ptr", "c", "2026-10-15T19:03:39Z", "12.1.7", 70424)}
    a = stale_alerts(heads, now)
    assert [x.key for x in a] == ["stale:forever"]
    assert "no new export for 14.0 days" in a[0].message and "Meanwhile live exported 12.1.5.70500" in a[0].message
    a = stale_alerts(heads, now, 10)  # every branch: ptr is stale too, live is not
    assert [x.key for x in a] == ["stale:forever", "stale:ptr"]
    assert stale_alerts(heads, now, None, {"forever": 0}) == []


def test_branch_set_and_exporter_alerts():
    assert branch_set_alerts(None, ["forever", "live"]) == []
    a = branch_set_alerts(["forever", "live", "classic_beta"], ["forever", "live", "wowf"])
    assert [x.key for x in a] == ["new-branch:wowf", "removed-branch:classic_beta"]
    assert parse_exporter_products(EXPORTER_PS1) == ["wow", "wow_anniversary", "wow_classic", "wow_classic_beta",
                                                     "wow_classic_era", "wowt"]
    assert parse_exporter_products("no param block") is None
    assert exporter_alerts(None, ["wow"]) == []
    a = exporter_alerts(["wow", "wow_classic_beta"], ["wow", "wow_classic_beta", "wowf"])
    assert [x.key for x in a] == ["exporter-added:wowf"]
    assert parse_export_product(EXPORT_YML.format(product="wow_classic_beta")) == "wow_classic_beta"
    assert parse_export_product("name: x\n") is None
    assert export_product_alert("forever", None, "wow_classic_beta") == []
    assert [x.key for x in export_product_alert("forever", "wow_classic_beta", "wowf")] == ["export-product:forever:wowf"]


# ------------------------------------------------------------------ git-backed CLI tests
def test_check_missing_branch_warns_and_optional_exit(fake_mirror, tmp_path, capsys):
    out, state = tmp_path / "out", tmp_path / "state.json"
    common = ["--cache-dir", tmp_path / "cache", "--repo-url", fake_mirror["url"]]
    chk = ["check", "--state", state, "--branches", "forever,nosuchbranch", "--out-dir", out,
           "--now", "2026-10-02T00:00:00Z"]
    assert run_cli(*common, *chk) == 0  # a warning, not an error, by default
    err = capsys.readouterr().err
    assert "WARNING: nosuchbranch: branch is not in the mirror" in err
    s = summary(out)
    assert s["branches"]["nosuchbranch"]["status"] == "missing-branch"
    assert s["branches"]["forever"]["status"] == "baseline-recorded"  # the other branch still works
    assert kinds(s) == ["missing:nosuchbranch"] and s["new_alerts"] == ["missing:nosuchbranch"]
    assert "nosuchbranch" in (out / "alerts.md").read_text(encoding="utf-8")
    # the optional non-zero exit; the alert is known now, so it is no longer "new"
    assert run_cli(*common, *chk, "--fail-on-alert", "missing") == 4
    s = summary(out)
    assert s["fail_alert"] is True and s["new_alerts"] == []
    # offline: a branch missing from the cache is reported the same way
    assert run_cli("--offline", "--cache-dir", tmp_path / "cache", *chk, "--fail-on-alert", "missing") == 4
    assert "not in the local cache" in capsys.readouterr().err
    # without missing branches the exit code stays 0
    assert run_cli(*common, "check", "--state", state, "--branches", "forever", "--out-dir", out,
                   "--now", "2026-10-02T00:00:00Z", "--fail-on-alert", "missing") == 0


def test_check_stale_branch(fake_mirror, tmp_path, capsys):
    out, state = tmp_path / "out", tmp_path / "state.json"
    base = ["--cache-dir", tmp_path / "cache", "--repo-url", fake_mirror["url"], "check", "--state", state,
            "--branches", "forever", "--out-dir", out]
    # newest forever build: 2026-10-01 22:56 UTC; the built-in limit for forever is 10 days
    assert run_cli(*base, "--now", "2026-10-09T00:00:00Z") == 0
    assert summary(out)["alerts"] == []
    assert summary(out)["branches"]["forever"]["head_age_days"] == 7.0
    assert run_cli(*base, "--now", "2026-10-20T00:00:00Z") == 0
    s = summary(out)
    assert kinds(s) == ["stale:forever"] and s["new_alerts"] == ["stale:forever"]
    assert "forever: no new export for 18.0 days" in capsys.readouterr().err
    assert run_cli(*base, "--now", "2026-10-21T00:00:00Z") == 0
    assert summary(out)["new_alerts"] == []  # still stale, already reported
    assert run_cli(*base, "--now", "2026-10-20T00:00:00Z", "--stale-days", "forever=0") == 0
    assert summary(out)["alerts"] == []
    assert run_cli(*base, "--now", "2026-10-20T00:00:00Z", "--stale-days", "30") == 0
    assert summary(out)["alerts"] == []
    assert run_cli(*base, "--now", "2026-10-09T00:00:00Z", "--stale-days", "5", "--fail-on-alert", "any") == 4
    assert run_cli(*base, "--now", "2026-10-09T00:00:00Z", "--stale-days", "5", "--fail-on-alert", "missing") == 0


def test_check_forever_band_reused_slot(fake_mirror, tmp_path, capsys):
    out, state = tmp_path / "out", tmp_path / "state.json"
    base = ["--cache-dir", tmp_path / "cache", "--repo-url", fake_mirror["url"], "check", "--state", state,
            "--branches", "forever", "--out-dir", out, "--now", "2026-10-21T00:00:00Z", "--stale-days", "0"]
    assert run_cli(*base) == 0
    assert summary(out)["alerts"] == []
    commit_build(fake_mirror["path"], "new", "2.5.7", 200, "2026-10-20T10:00:00Z")
    assert run_cli(*base, "--fail-on-alert", "any") == 4
    s = summary(out)
    assert s["branches"]["forever"]["status"] == "new-build"  # the report still runs
    assert kinds(s) == ["band-change:forever:forever->tbc", "forever-band:tbc"]
    err = capsys.readouterr().err
    assert "forever: newest build 2.5.7.200 is not a WoW: Forever build (tbc)" in err


def test_check_mirror_branch_set_and_exporter(fake_mirror, tmp_path):
    repo = fake_mirror["path"]
    out, state = tmp_path / "out", tmp_path / "state.json"
    base = ["--cache-dir", tmp_path / "cache", "--repo-url", fake_mirror["url"], "check", "--state", state,
            "--branches", "forever", "--out-dir", out, "--now", "2026-10-21T00:00:00Z", "--stale-days", "0"]
    # the forever build carries its export workflow; an automation branch carries the exporter
    commit_build(repo, "new", "1.60.1", 103, "2026-10-02T10:00:00Z",
                 {".github/workflows/export.yml": EXPORT_YML.format(product="wow_classic_beta")})
    git(repo, "checkout", "-q", "--orphan", "automation")
    git(repo, "rm", "-rq", "--cached", ".")
    git(repo, "clean", "-fdqx")
    (repo / "ExportInterfaceFiles.ps1").write_text(EXPORTER_PS1, encoding="utf-8")
    git(repo, "add", "ExportInterfaceFiles.ps1")
    subprocess.run(["git", "commit", "-q", "-m", "Exporter"], cwd=repo, check=True, env=_env("2026-09-16T00:00:00Z"))
    git(repo, "checkout", "-q", "-f", "forever")
    assert run_cli(*base) == 0  # first run records branches, exporter products and the export product
    s = summary(out)
    assert s["alerts"] == [] and s["mirror"]["branches"] == ["automation", "forever"]
    assert s["mirror"]["exporter_products"][-1] == "wowt"
    assert s["branches"]["forever"]["export_product"] == "wow_classic_beta"
    # launch-like changes: a new branch, a new exporter product, forever re-pointed to it
    git(repo, "branch", "wowf", "forever")
    commit_file(repo, "automation", "ExportInterfaceFiles.ps1",
                EXPORTER_PS1.replace('"wowt")]', '"wowt", "wowf")]'), "Add wowf", "2026-10-20T00:00:00Z")
    git(repo, "checkout", "-q", "forever")
    commit_build(repo, "new", "1.60.1", 104, "2026-10-20T12:00:00Z",
                 {".github/workflows/export.yml": EXPORT_YML.format(product="wowf")})
    assert run_cli(*base) == 0
    s = summary(out)
    assert kinds(s) == ["export-product:forever:wowf", "exporter-added:wowf", "new-branch:wowf"]
    assert sorted(s["new_alerts"]) == kinds(s)
    md = (out / "alerts.md").read_text(encoding="utf-8")
    assert md.startswith("<!-- patchwatch:alerts -->") and "**(new)**" in md
    # the branch disappears again
    git(repo, "branch", "-D", "wowf")
    assert run_cli(*base) == 0
    assert kinds(summary(out)) == ["removed-branch:wowf"]
    st = json.loads(state.read_text(encoding="utf-8"))
    assert st["branches"]["forever"]["export_product"] == "wowf" and "wowf" in st["mirror"]["exporter_products"]
    # --no-exporter-check skips the automation branch
    assert run_cli(*base, "--no-exporter-check") == 0
    assert summary(out)["mirror"]["exporter_products"] is None


def test_other_commands_report_missing_branches(fake_mirror, tmp_path, capsys):
    common = ["--cache-dir", tmp_path / "cache", "--repo-url", fake_mirror["url"]]
    assert run_cli(*common, "fetch", "--branches", "forever,nosuchbranch") == 0
    captured = capsys.readouterr()
    assert "(not in mirror)" in captured.out and "WARNING: nosuchbranch" in captured.err
    assert run_cli(*common, "builds", "--branches", "forever,nosuchbranch") == 0
    assert "nosuchbranch: branch is not in the mirror" in capsys.readouterr().err
    assert run_cli(*common, "diff", "forever@first", "nosuchbranch") == 1
    assert "is not in the mirror" in capsys.readouterr().err
