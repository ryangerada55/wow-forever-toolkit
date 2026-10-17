"""Git-backed tests: a local repo shaped like the mirror is served as a partial-clone remote."""
import json
import subprocess
import sys

import pytest
from conftest import ROOT, commit_tree, make_tree

from patchwatch import cli
from patchwatch.mirror import Build, Mirror, MirrorError, default_cache_dir, interface_number, parse_subject


def run_cli(*args):
    return cli.main([str(a) for a in args])


def test_interface_and_subject_parsing():
    assert interface_number("1.60.1") == 16001
    assert interface_number("12.1.5") == 120105
    assert interface_number("1.15.9") == 11509
    assert interface_number("3.80.2") == 38002
    assert parse_subject("12.1.5 (70391)") == ("12.1.5", 70391)
    assert parse_subject("Initial commit") == (None, None)


def test_build_labels():
    assert Build("forever", "b401e0332adf", "", "1.60.1", 70425).label == "1.60.1.70425"
    assert Build("live", "0123456789abcdef", "", None, None).label == "012345678"
    # a dir: source without version.txt keeps its whole path, so two such builds stay distinguishable
    assert Build(None, "dir:../trees/classic_era", "", None, None).label == "dir:../trees/classic_era"
    assert Build(None, "dir:../trees/forever", "", "1.60.1", 70425).label == "1.60.1.70425"


@pytest.mark.parametrize("platform,env,expect", [
    ("win32", {"LOCALAPPDATA": r"C:\Users\Jane Doe\AppData\Local"}, ("patchwatch", "Cache")),
    ("darwin", {}, ("Library", "Caches", "patchwatch")),
    ("linux", {"XDG_CACHE_HOME": "/tmp/x cache"}, ("x cache", "patchwatch")),
])
def test_default_cache_dir(monkeypatch, platform, env, expect):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.delenv("PATCHWATCH_CACHE_DIR", raising=False)
    for k in ("LOCALAPPDATA", "APPDATA", "XDG_CACHE_HOME"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    p = default_cache_dir()
    assert tuple(p.parts[-len(expect):]) == expect
    monkeypatch.setenv("PATCHWATCH_CACHE_DIR", "/some where/pw")
    assert default_cache_dir().as_posix().endswith("some where/pw")


def test_mirror_fetch_builds_resolve_and_read(fake_mirror, tmp_path):
    m = Mirror(tmp_path / "cache dir" / "wow-ui-source.git", url=fake_mirror["url"])
    m.fetch(["forever"])
    assert m.is_partial()
    builds = m.builds("forever", with_files=True)
    assert [b.build for b in builds] == [100, 101, 102]  # "Initial commit" is not a build
    assert builds[0].interface == 16001
    assert builds[-1].api_doc_files_changed == 2 and builds[1].api_doc_files_changed == 0
    assert m.resolve("forever").build == 102
    assert m.resolve("forever@first").build == 100
    assert m.resolve("forever@-1").build == 101
    assert m.resolve("forever@100").commit == fake_mirror["commits"][100]
    assert m.resolve("forever@1.60.1").build == 102
    assert m.resolve("forever@2026-09-20").build == 101
    assert m.resolve(fake_mirror["commits"][100][:12]).build == 100
    with pytest.raises(MirrorError):
        m.resolve("forever@999")
    files = m.read_dir(fake_mirror["commits"][100], "Interface/AddOns/Blizzard_APIDocumentationGenerated")
    assert sorted(files) == ["FooDocumentation.lua", "UnitFooDocumentation.lua"]
    assert "RemovedThing" in files["FooDocumentation.lua"]
    assert m.read_text(fake_mirror["commits"][102], "version.txt").strip() == "1.60.1.102"
    after = m.builds("forever", after=fake_mirror["commits"][100])
    assert [b.build for b in after] == [101, 102]


def test_cli_check_end_to_end(fake_mirror, tmp_path, addon_dir, capsys):
    cache = tmp_path / "my cache"
    state = tmp_path / "state dir" / "state.json"
    out = tmp_path / "out dir"
    common = ["--cache-dir", cache, "--repo-url", fake_mirror["url"]]
    # first run: record baseline only
    rc = run_cli(*common, "check", "--state", state, "--branches", "forever", "--out-dir", out,
                 "--addon", addon_dir.parent)
    assert rc == 0
    st = json.loads(state.read_text())
    assert st["branches"]["forever"]["build"] == 102
    summary = json.loads((out / "summary.json").read_text())
    assert summary["branches"]["forever"]["status"] == "baseline-recorded"
    # no new build
    assert run_cli(*common, "check", "--state", state, "--branches", "forever", "--out-dir", out) == 0
    assert json.loads((out / "summary.json").read_text())["branches"]["forever"]["status"] == "no-new-build"
    # compare from the first build, fail on addon impact
    rc = run_cli(*common, "check", "--state", state, "--branches", "forever", "--out-dir", out,
                 "--addon", addon_dir, "--since", "first", "--fail-on", "impact", "--no-update-state")
    assert rc == 3
    summary = json.loads((out / "summary.json").read_text())
    b = summary["branches"]["forever"]
    assert b["status"] == "new-build" and b["notify"] is True and b["new_builds"] == 2
    assert summary["notify_branches"] == ["forever"]
    md = (out / "forever.md").read_text()
    assert md.startswith("<!-- patchwatch:branch=forever -->")
    assert "C_Foo.RemovedThing" in md and "FOO_REMOVED" in md and "WOW_PROJECT_CAMELOT" in md
    assert "PatchwatchFixture_Camelot.toc" in md and "outdated" in md
    rep = json.loads((out / "forever.json").read_text())
    assert rep["addons"][0]["toc"]["status"] == "outdated"
    # a new build lands upstream: the next run reports exactly it
    c103 = commit_tree(fake_mirror["path"], "new", "1.60.2", 103, "2026-10-20T10:00:00Z")
    rc = run_cli(*common, "check", "--state", state, "--branches", "forever", "--out-dir", out,
                 "--addon", addon_dir, "--notify-on", "api")
    assert rc == 0
    b = json.loads((out / "summary.json").read_text())["branches"]["forever"]
    assert b["new_builds"] == 1 and b["interface_changed"] is True and b["notify"] is True
    assert "16001 -> **16002**" in (out / "forever.md").read_text()
    assert json.loads(state.read_text())["branches"]["forever"]["build"] == 103
    # parsed snapshots are cached gzipped and pruned to what the state still needs plus recent ones
    snaps = sorted(p.name for p in (cache / "snapshots").iterdir())
    assert f"{c103}.json.gz" in snaps and len(snaps) <= 2


def test_cli_diff_dirs_and_scan(tmp_path, addon_dir, capsys):
    old = make_tree(tmp_path / "old snap", "old", "1.60.1.100")
    new = make_tree(tmp_path / "new snap", "new", "1.60.1.102")
    md = tmp_path / "r.md"
    js = tmp_path / "r.json"
    rc = run_cli("--offline", "--cache-dir", tmp_path / "c", "diff", f"dir:{old}", f"dir:{new}",
                 "--addon", addon_dir, "--md", md, "--json", js, "--fail-on", "breaking")
    assert rc == 3
    rep = json.loads(js.read_text())
    assert rep["comparison"]["api"]["functions"]["removed"] == ["C_Foo.RemovedThing"]
    assert rep["comparison"]["deprecated"]["removed"] == ["Mainline/Deprecated_1_0_0.lua"]
    assert "WOW_PROJECT_CAMELOT" in rep["comparison"]["project_constants"]["added"]
    # pointing straight at a docs folder also works
    rc = run_cli("--offline", "diff", f"dir:{old / 'Interface/AddOns/Blizzard_APIDocumentationGenerated'}",
                 f"dir:{new / 'Interface/AddOns/Blizzard_APIDocumentationGenerated'}", "--json", js)
    assert rc == 0 and json.loads(js.read_text())["comparison"]["api"]["counts"]["functions_removed"] == 1
    rc = run_cli("--offline", "scan", addon_dir, "--build", f"dir:{new}", "--compare", f"dir:{old}",
                 "--json", js, "--fail-on", "impact")
    assert rc == 3
    rep = json.loads(js.read_text())
    assert rep["addons"][0]["toc"]["status"] == "outdated"


def test_module_entry_point_and_usage_errors(tmp_path):
    r = subprocess.run([sys.executable, "-m", "patchwatch", "--version"], cwd=ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0 and b"patchwatch" in r.stdout
    r = subprocess.run([sys.executable, "-m", "patchwatch", "diff"], cwd=ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 2
    r = subprocess.run([sys.executable, "-m", "patchwatch", "--offline", "--cache-dir", str(tmp_path / "none"),
                        "diff", "forever@first", "forever"], cwd=ROOT, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    assert r.returncode == 1 and b"error" in r.stderr


def test_markdown_fits_issue_limit():
    from patchwatch.report import render_markdown
    big = {f"C_X.F{i}": {} for i in range(5000)}
    cmp = {"old": {"label": "a"}, "new": {"label": "b"}, "interface": {"old": 1, "new": 1, "changed": False},
           "api": {"functions": {"added": sorted(big), "removed": sorted(big), "changed": {}, "rename_hints": {}},
                   "events": {"added": [], "removed": [], "changed": {}},
                   "tables": {"added": [], "removed": [], "changed": {}, "removed_types": {}, "added_types": {}},
                   "counts": {k: 0 for k in ("functions_added", "functions_removed", "functions_changed",
                                             "events_added", "events_removed", "events_changed", "tables_added",
                                             "tables_removed", "tables_changed", "restriction_changes",
                                             "restrictions_tightened", "restrictions_loosened", "breaking")}},
           "deprecated": {"added": [], "removed": [], "changed": {}, "names_added": {}, "names_removed": {}},
           "project_constants": {"added": {}, "removed": {}, "changed": {}}}
    md = render_markdown({"comparison": cmp, "branch": "x"}, max_chars=20000)
    assert len(md) <= 20000 and "more (see the JSON report)" in md
