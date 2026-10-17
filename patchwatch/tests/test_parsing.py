from conftest import FIX

from patchwatch.lualex import decode_string, tokenize
from patchwatch.luatable import Expr, parse_documentation_file, parse_value, registered_tables


def test_tokenize_skips_comments_and_decodes_strings():
    src = '--[==[ block C_Foo.X ]==] local a = "x\\"y" -- line\nb = [[raw\nstr]] c = 0x1F d = 1.5e3'
    toks = [(t.kind, t.value) for t in tokenize(src)]
    assert ("string", 'x"y') in toks
    assert ("string", "raw\nstr") in toks
    assert ("number", "0x1F") in toks
    assert not any("C_Foo" in v for _, v in toks)


def test_decode_escapes():
    assert decode_string(r'"a\tb\65\x41\z   c"') == "a\tbAAc"
    assert decode_string("[==[\nkeep ]] this]==]") == "keep ]] this"


def test_parse_values():
    assert parse_value("{ 1, 2, 3 }") == [1, 2, 3]
    assert parse_value("{ a = true, b = nil, c = -4 }") == {"a": True, "b": None, "c": -4}
    v = parse_value("{ Default = Enum.A.B + Enum.A.C, x = NUM_BAG_SLOTS }")
    assert isinstance(v["Default"], Expr) and v["Default"] == "Enum.A.B + Enum.A.C"
    assert v["x"] == "NUM_BAG_SLOTS"
    assert parse_value('{ [1] = "a", ["k"] = 2; "b" }') == {1: "b", "k": 2}


def test_documentation_file_registration():
    src = (FIX / "docs_old" / "UnitFooDocumentation.lua").read_text()
    tables, registered, errors = parse_documentation_file(src)
    assert registered == ["UnitFoo", "FooFrameAPI"]
    assert not errors
    regs, errs = registered_tables(src)
    assert [t["Name"] for t in regs] == ["UnitFoo", "FooFrameAPI"]


def test_parser_recovers_from_broken_table():
    src = 'local Bad = { Name = "x", = }\nlocal Good = { Name = "ok" }\nAPIDocumentation:AddDocumentationTable(Good);'
    regs, errs = registered_tables(src)
    assert [t["Name"] for t in regs] == ["ok"]
    assert errs and errs[0].startswith("Bad")
