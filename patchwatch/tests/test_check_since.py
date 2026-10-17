"""check --since on a branch with too few builds, and the addon name of a relative --addon path."""
import json
import shutil
from pathlib import Path

from conftest import git, make_tree
from test_alerts import commit_build

from patchwatch import cli
from patchwatch.toc import addon_display_name


def run_cli(*args):
    return cli.main([str(a) for a in args])


def test_check_since_with_too_few_builds_records_a_baseline(fake_mirror, tmp_path, capsys):
    # A branch that is new to the mirror has one build (the launch product's branch on launch day,
    # or a shallow mirror copy). "--since -1" used to stop the whole run with exit 1.
    repo = fake_mirror["path"]
    git(repo, "checkout", "-q", "--orphan", "wowf")
    commit_build(repo, "new", "1.60.1", 200, "2026-10-15T19:00:00Z")
    git(repo, "checkout", "-q", "forever")
    out, state = tmp_path / "out", tmp_path / "state.json"
    rc = run_cli("--cache-dir", tmp_path / "cache", "--repo-url", fake_mirror["url"], "check", "--state", state,
                 "--branches", "forever,wowf", "--out-dir", out, "--since", "-1", "--now", "2026-10-16T00:00:00Z")
    assert rc == 0
    err = capsys.readouterr().err
    assert "wowf: --since -1: wowf@-1: only 1 builds on wowf; recorded the current build as the baseline" in err
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert s["branches"]["forever"]["status"] == "new-build"  # 1.60.1.101 -> 1.60.1.102
    assert s["branches"]["forever"]["old"]["build"] == 101 and s["branches"]["forever"]["new"]["build"] == 102
    assert s["branches"]["wowf"]["status"] == "baseline-recorded"
    assert "only 1 builds" in s["branches"]["wowf"]["note"]
    st = json.loads(state.read_text(encoding="utf-8"))
    assert st["branches"]["wowf"]["build"] == 200  # the next run compares from here
    # a date before the branch's first build is handled the same way
    rc = run_cli("--cache-dir", tmp_path / "cache", "--repo-url", fake_mirror["url"], "check", "--state", state,
                 "--branches", "wowf", "--out-dir", out, "--since", "2026-01-01", "--now", "2026-10-16T00:00:00Z")
    assert rc == 0 and "no build on or before 2026-01-01" in capsys.readouterr().err
    # a malformed spec is still an error
    rc = run_cli("--cache-dir", tmp_path / "cache", "--repo-url", fake_mirror["url"], "check", "--state", state,
                 "--branches", "wowf", "--out-dir", out, "--since", "soon", "--now", "2026-10-16T00:00:00Z")
    assert rc == 1


def test_relative_addon_path_reports_the_addon_name(tmp_path, addon_dir, monkeypatch):
    # "--addon ." (the workflow's default PATCHWATCH_ADDON_PATH) gave an empty "#### " heading.
    work = tmp_path / "PatchwatchFixture"
    shutil.copytree(addon_dir, work)
    new = make_tree(tmp_path / "new snap", "new", "1.60.1.102")
    old = make_tree(tmp_path / "old snap", "old", "1.60.1.100")
    monkeypatch.chdir(work)
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    rc = run_cli("--offline", "diff", f"dir:{old}", f"dir:{new}", "--addon", ".", "--md", md, "--json", js)
    assert rc == 0
    rep = json.loads(js.read_text(encoding="utf-8"))
    assert rep["addons"][0]["addon"] == "PatchwatchFixture"
    assert rep["addons"][0]["toc"]["addon"] == "PatchwatchFixture"
    text = md.read_text(encoding="utf-8")
    assert "#### PatchwatchFixture" in text and "#### \n" not in text


def test_addon_display_name_prefers_the_toc_name_for_a_checkout_folder(tmp_path):
    checkout = tmp_path / "wow-addon-sample"
    checkout.mkdir()
    (checkout / "HelloAzeroth.toc").write_text("## Interface: 16001\nCore.lua\n", encoding="utf-8")
    assert addon_display_name(checkout) == "HelloAzeroth"
    named = tmp_path / "Tx_Bags"
    named.mkdir()
    (named / "Tx_Bags.toc").write_text("## Interface: 16001\n", encoding="utf-8")
    (named / "Tx_Bags_Camelot.toc").write_text("## Interface: 16001\n", encoding="utf-8")
    assert addon_display_name(named) == "Tx_Bags"
    assert addon_display_name(Path(tmp_path / "missing")) == "missing"
