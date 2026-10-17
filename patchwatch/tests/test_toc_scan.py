import pytest
from conftest import FIX

from patchwatch.apidocs import build_model
from patchwatch.scan import KnownNames, assess_impact, scan_addon, scan_lua
from patchwatch.snapshot import compare_snapshots, shim_names
from patchwatch.toc import check_addon, game_type_for_interface, parse_toc, select_toc


@pytest.mark.parametrize("iface,gt", [
    (16001, "forever"), (16100, "forever"), (11509, "classic"), (20506, "bcc"), (30405, "wrath"),
    (38002, "titan"), (40402, "cata"), (50504, "mists"), (120105, "retail"), (120107, "retail"),
])
def test_game_type_for_interface(iface, gt):
    assert game_type_for_interface(iface) == gt


def test_parse_toc_bom_lists_and_typed_lines(addon_dir):
    t = parse_toc(addon_dir / "PatchwatchFixture_Camelot.toc")
    assert t["suffix"] == "Camelot" and t["base"] == "PatchwatchFixture"
    assert t["interfaces"] == [16000]
    assert t["typed_interfaces"] == {"forever": [16000]}
    main = parse_toc(addon_dir / "PatchwatchFixture.toc")
    assert main["interfaces"] == [120100, 16001]
    assert main["files"][-1]["conditions"] == [("allow", ["forever"])]


def test_select_toc(addon_dir):
    from patchwatch.toc import addon_tocs
    tocs = addon_tocs(addon_dir)
    assert select_toc(tocs, "forever", "PatchwatchFixture")["name"] == "PatchwatchFixture_Camelot.toc"
    assert select_toc(tocs, "retail", "PatchwatchFixture")["name"] == "PatchwatchFixture.toc"
    assert select_toc(tocs, "classic", "PatchwatchFixture")["name"] == "PatchwatchFixture.toc"


def test_check_addon_statuses(addon_dir):
    r = check_addon(addon_dir, "forever", 16001, "forever")
    assert r["selected_toc"] == "PatchwatchFixture_Camelot.toc"
    assert r["status"] == "outdated"
    assert r["suggested_line"] == "## Interface: 16000, 16001"
    sel = [t for t in r["tocs"] if t["selected"]][0]
    assert any("Interface-Forever" in n for n in sel.get("notes", []))
    assert any("AllowLoadGameType forever" in l for l in r["lint"])
    retail = check_addon(addon_dir, "retail", 120105, "live")
    assert retail["status"] == "outdated" and retail["suggested_line"] == "## Interface: 16001, 120100, 120105"
    assert check_addon(addon_dir, "retail", 120100)["status"] == "ok"
    era = check_addon(addon_dir, "classic", 11509)
    assert era["status"] == "not-declared"


def _snap(which):
    d = FIX / f"docs_{which}"
    api = build_model({p.name: p.read_text(encoding="utf-8") for p in d.glob("*.lua")})
    dep = {}
    for p in (FIX / f"deprecated_{which}").rglob("*.lua"):
        dep[p.relative_to(FIX / f"deprecated_{which}").as_posix()] = {
            "names": shim_names(p.read_text()), "guarded_by_cvar": True, "toc_condition": "", "in_toc": True}
    consts = {"WOW_PROJECT_MAINLINE": [{"file": "ProjectConstants.lua", "value": "1", "toc_condition": ""}]}
    if which == "new":
        consts["WOW_PROJECT_CAMELOT"] = [{"file": "Camelot/ProjectConstants.lua", "value": "18",
                                          "toc_condition": "[AllowLoadGameType camelot]"}]
    return {"build": {"label": which, "interface": 16001}, "api": api, "deprecated": dep,
            "project_constants": consts, "has_docs": True}


def test_shim_names():
    src = (FIX / "deprecated_old" / "Mainline" / "Deprecated_1_0_0.lua").read_text()
    assert shim_names(src) == ["C_Foo.OldAlias", "GetOldFoo"]


def test_scan_lua_detection(addon_dir):
    old, new = _snap("old"), _snap("new")
    known = KnownNames.from_snapshots([old, new])
    sc = scan_addon(addon_dir, known)
    r = sc["refs"]
    assert "C_Foo.RemovedThing" in r["functions"]
    assert "C_Foo.GetThing" in r["functions"]  # bracket access
    assert "UnitFoo" in r["functions"]
    assert r["functions"]["C_Foo.StatFunc"]["locations"][0]["file"] == "UI.xml"
    assert r["functions"]["C_Foo.StatFunc"]["count"] == 1  # the Lua string mention is ignored
    assert r["functions"]["C_Foo.ChangedArgs"]["locations"][0]["lib"] is True  # comment/long string ignored
    assert r["events"]["FOO_REMOVED"]["locations"][0]["kind"] == "register"
    assert "FOO_UPDATED" in r["events"]
    assert "Enum.FooType.C" in r["table_fields"]
    assert {"WOW_PROJECT_CAMELOT", "WOW_PROJECT_MAINLINE"} - set(known.globals) == set()
    assert "WOW_PROJECT_CAMELOT" in r["constants"]
    xml_attr = [l for l in r["functions"]["UnitFoo"]["locations"] if l["kind"] == "xml-attr"]
    assert xml_attr and xml_attr[0]["file"] == "UI.xml"


def test_scan_ignores_local_definitions():
    known = KnownNames()
    known.globals.update({"GetTime"})
    known.functions.update({"GetTime"})
    out = {"functions": {}, "events": {}, "tables": {}, "table_fields": {}, "constants": {}, "defines": {}}
    scan_lua("local a, GetTime = 1, 2\nlocal function GetTime() end\nfunction GetTime() end\nx = GetTime()",
             "x.lua", known, out)
    assert out["functions"]["GetTime"]["count"] == 1
    assert out["defines"]["GetTime"]["count"] == 1


def test_impact(addon_dir):
    old, new = _snap("old"), _snap("new")
    cmp = compare_snapshots(old, new)
    known = KnownNames.from_snapshots([old, new])
    sc = scan_addon(addon_dir, known)
    from patchwatch.snapshot import deprecated_names
    findings = assess_impact(sc, cmp, deprecated_names(new))
    by = {(f["kind"], f["name"]): f for f in findings}
    # removed from docs but still shimmed in the new build -> warning, with replacement hint
    rt = by[("function", "C_Foo.RemovedThing")]
    assert rt["severity"] == "warning" and "Blizzard_Deprecated" in rt["what"]
    assert rt["replacements"] == ["C_Foo.RemovedThingV2"]
    assert by[("event", "FOO_REMOVED")]["severity"] == "breaking"
    assert by[("table-field", "Enum.FooType.C")]["severity"] == "breaking"
    assert by[("function", "C_Foo.ChangedArgs")]["only_in_libraries"] is True
    assert by[("function", "UnitFoo")]["severity"] == "breaking"  # SecretReturns added
    assert by[("constant", "WOW_PROJECT_CAMELOT")]["severity"] == "info"
    assert findings[0]["severity"] == "breaking"
    wm = by[("widget-method", "FooFrameAPI:SetScript")]  # matched by method name only
    assert wm["severity"] == "info" and "loosened" in wm["what"] and wm["locations"][0]["file"] == "Core.lua"


def test_stub_toc_is_not_supported(tmp_path):
    d = tmp_path / "Stub Addon"
    d.mkdir()
    (d / "Stub Addon.toc").write_text("## Interface: 00000\n## Title: unsupported client\n")
    (d / "Stub Addon_Camelot.toc").write_text("## Interface: 16001\n")
    assert check_addon(d, "retail", 120105)["status"] == "not-supported"
    assert check_addon(d, "forever", 16001)["status"] == "ok"


def _addon(tmp_path, files):
    d = tmp_path / "TxProbe"
    d.mkdir()
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


def test_client_toc_order_follows_real_clients(tmp_path):
    # wowless (real clients): Forever reads _Camelot, then _Forever, then _Mainline, then the bare TOC;
    # retail reads _Standard before _Mainline.
    d = _addon(tmp_path, {"TxProbe.toc": "## Interface: 16001\n",
                          "TxProbe_Mainline.toc": "## Interface: 120105\n",
                          "TxProbe_Standard.toc": "## Interface: 120105, 120107\n"})
    r = check_addon(d, "forever", 16001)
    assert r["selected_toc"] == "TxProbe_Mainline.toc" and r["status"] == "not-declared"
    assert check_addon(d, "retail", 120107)["selected_toc"] == "TxProbe_Standard.toc"
    (d / "TxProbe_Camelot.toc").write_text("## Interface: 16001\n", encoding="utf-8")
    r = check_addon(d, "forever", 16001)
    assert r["selected_toc"] == "TxProbe_Camelot.toc" and r["status"] == "ok"
    assert {t["toc"]: t["status"] for t in r["tocs"]}["TxProbe_Mainline.toc"] == "not-loaded"


def test_game_type_gate_and_stub_lint(tmp_path):
    gate = "## Interface: 16001\n## AllowLoadGameType: camelot\n## ExcludeLoadGameType: standard, classic\nCore.lua\n"
    d = _addon(tmp_path, {"TxProbe.toc": gate})
    r = check_addon(d, "forever", 16001)
    assert r["status"] == "ok" and r["lint"] == []
    assert parse_toc(d / "TxProbe.toc")["gates"] == {"allow": ["camelot"], "exclude": ["standard", "classic"]}
    (d / "TxProbe.toc").write_text("## Interface: 16001\n## AllowLoadGameType: camelot, forever\nCore.lua\n"
                                   "A.lua [AllowLoadGameType camelot]\n"
                                   "B.lua [AllowLoadGameType camelot][ExcludeLoadGameType standard, classic]\n",
                                   encoding="utf-8")
    (d / "TxProbe_Vanilla.toc").write_text("## Interface: 00000\n", encoding="utf-8")
    lint = check_addon(d, "forever", 16001)["lint"]
    assert any("'## AllowLoadGameType: camelot, forever' without" in x for x in lint)
    assert any(x.startswith("TxProbe.toc:4: [AllowLoadGameType camelot] without") for x in lint)
    assert not any(x.startswith("TxProbe.toc:5:") for x in lint)
    assert any(x.startswith("TxProbe_Vanilla.toc: an Interface 00000") for x in lint)
