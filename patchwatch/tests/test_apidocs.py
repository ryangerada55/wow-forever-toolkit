import pytest
from conftest import FIX

from patchwatch.apidocs import build_model, diff_models, iter_restriction_changes


def _model(which):
    d = FIX / f"docs_{which}"
    return build_model({p.name: p.read_text(encoding="utf-8") for p in d.glob("*.lua")})


@pytest.fixture(scope="module")
def models():
    return _model("old"), _model("new")


@pytest.fixture(scope="module")
def diff(models):
    return diff_models(*models)


def test_qualified_names(models):
    old, _ = models
    assert "C_Foo.GetThing" in old["functions"]
    assert "UnitFoo" in old["functions"]  # global system without Namespace
    assert "FooFrameAPI:SetScript" in old["functions"]  # widget method
    assert "FOO_UPDATED" in old["events"]
    assert "Enum.FooType" in old["tables"] and "FooInfo" in old["tables"]
    assert "SecretWhenFooRestricted" in old["predicates"]
    assert old["errors"] == []
    flags = [f for f in old["tables"]["FooInfo"]["fields"] if f["name"] == "flags"][0]
    assert flags["attrs"]["Default"] == "Enum.FooType.A + Enum.FooType.B"


def test_added_removed_and_hints(diff):
    assert diff["functions"]["removed"] == ["C_Foo.RemovedThing"]
    assert diff["functions"]["added"] == ["C_Foo.RemovedThingV2"]
    assert diff["functions"]["rename_hints"]["C_Foo.RemovedThing"] == ["C_Foo.RemovedThingV2"]
    assert diff["events"]["removed"] == ["FOO_REMOVED"]
    assert diff["events"]["added"] == ["FOO_ADDED"]


def test_signature_changes_and_severity(diff):
    ch = diff["functions"]["changed"]
    args = ch["C_Foo.ChangedArgs"]["args"]
    assert args == [{"change": "added", "index": 2, "name": "mode", "new": "number", "severity": "breaking"}]
    assert ch["C_Foo.ChangedArgs"]["severity"] == "breaking"
    rets = {r["change"]: r for r in ch["C_Foo.GetThing"]["returns"]}
    assert rets["type"]["severity"] == "info"  # cstring -> string
    assert rets["nilable"]["severity"] == "warning"  # may now return nil
    assert "Documentation" not in str(ch["C_Foo.GetThing"]["attrs"])


def test_restriction_changes(diff):
    rows = {(q, r.get("key")): r for _, q, r in iter_restriction_changes(diff)}
    assert rows[("C_Foo.StatFunc", "SecretWhenFooRestricted")]["direction"] == "tightened"
    assert rows[("UnitFoo", "SecretReturns")]["direction"] == "tightened"
    sa = rows[("FooFrameAPI:SetScript", "SecretArguments")]
    assert (sa["old"], sa["new"], sa["direction"]) == ("NotAllowed", "AllowedWhenUntainted", "loosened")
    payload = rows[("FOO_UPDATED", "ConditionalSecret")]
    assert payload["where"] == "payload" and payload["direction"] == "tightened"
    c = diff["counts"]
    assert c["restrictions_tightened"] == 3 and c["restrictions_loosened"] == 1


def test_enum_and_structure_changes(diff):
    t = diff["tables"]["changed"]
    enum = {r["name"]: r for r in t["Enum.FooType"]["fields"]}
    assert enum["C"]["change"] == "removed" and enum["C"]["severity"] == "breaking"
    info = {(r["change"], r["name"]) for r in t["FooInfo"]["fields"]}
    assert ("removed", "label") in info and ("added", "text") in info


def test_identical_models_have_no_changes(models):
    old, _ = models
    d = diff_models(old, old)
    assert d["counts"]["breaking"] == 0
    assert not any(v for k, v in d["counts"].items())
