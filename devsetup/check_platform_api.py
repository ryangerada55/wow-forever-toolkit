#!/usr/bin/env python3
"""check_platform_api.py - prove that every WoW API call in a Lua file exists on a client branch.

Reads Blizzard's UI source mirror (a git clone of https://github.com/Gethe/wow-ui-source; no
checkout needed) and classifies each global function, C_ namespace function and widget method
that a Lua file calls:

  doc      declared in Blizzard_APIDocumentationGenerated (C API, incl. widget methods)
  lua      defined as a global function in Blizzard's Lua (FrameXML/SharedXML helpers)
  used     neither, but Blizzard's own code on that branch calls it (older undocumented C API)
  MISSING  none of the above -> not safe to call on that branch

Usage:
  python3 check_platform_api.py --ui-source ~/src/wow-ui-source [--branch origin/forever ...] FILE.lua

Exit status 1 if anything is MISSING on the first --branch. Standard library only.
"""
import argparse
import re
import subprocess
import sys

LUA_KEYWORDS = {"and", "break", "do", "else", "elseif", "end", "false", "for", "function", "if", "in",
                "local", "nil", "not", "or", "repeat", "return", "then", "true", "until", "while"}
LUA_STD = {"assert", "error", "ipairs", "next", "pairs", "pcall", "print", "rawget", "rawset", "select",
           "setmetatable", "getmetatable", "tonumber", "tostring", "type", "unpack", "xpcall"}
LUA_STD_LIBS = {"table", "string", "math", "coroutine", "bit"}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True, check=True).stdout.decode("utf-8", "replace")


def strip_lua(src):
    """Remove comments and string contents so names inside them are not counted."""
    out, i, n = [], 0, len(src)
    while i < n:
        if src.startswith("--", i):
            m = re.match(r"\[(=*)\[", src[i + 2:])
            if m:
                end = src.find("]" + m.group(1) + "]", i)
                i = n if end < 0 else end + len(m.group(1)) + 2
            else:
                end = src.find("\n", i)
                i = n if end < 0 else end
            continue
        m = re.match(r"\[(=*)\[", src[i:])
        if m:
            end = src.find("]" + m.group(1) + "]", i + len(m.group(0)))
            out.append('""')
            i = n if end < 0 else end + len(m.group(1)) + 2
            continue
        if src[i] in "\"'":
            q, j = src[i], i + 1
            while j < n and src[j] != q:
                j += 2 if src[j] == "\\" else 1
            out.append('""')
            i = j + 1
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def calls_in(path):
    code = strip_lua(open(path, encoding="utf-8").read())
    local_names = set(re.findall(r"\blocal\s+function\s+([A-Za-z_]\w*)", code))
    for decl in re.findall(r"\blocal\s+([A-Za-z_][\w\s,]*?)\s*=", code):
        local_names.update(x.strip() for x in decl.split(","))
    for params in re.findall(r"function\b[^(]*\(([^)]*)\)", code):
        local_names.update(p.strip() for p in params.split(",") if p.strip())
    defined_tables = set(re.findall(r"\bfunction\s+([A-Za-z_]\w*)[.:]", code))
    globals_, namespaced, methods = set(), set(), set()
    for m in re.finditer(r"(?<![\w.:])([A-Za-z_]\w*)\s*\(", code):
        name = m.group(1)
        if name in LUA_KEYWORDS or name in LUA_STD or name in local_names:
            continue
        prev = code[:m.start()].rstrip()
        if prev.endswith("function"):
            continue
        globals_.add(name)
    for m in re.finditer(r"(?<![\w.:])([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*\(", code):
        ns, fn = m.groups()
        if ns in LUA_STD_LIBS or ns in local_names or ns in defined_tables:
            continue
        namespaced.add(ns + "." + fn)
    for m in re.finditer(r":([A-Za-z_]\w*)\s*\(", code):
        methods.add(m.group(1))
    return sorted(globals_), sorted(namespaced), sorted(methods)


def index_branch(repo, branch):
    doc_globals, doc_ns, doc_methods = set(), set(), set()
    prefix = "Interface/AddOns/Blizzard_APIDocumentationGenerated/"
    files = [f for f in git(repo, "ls-tree", "-r", "--name-only", branch, prefix).splitlines() if f.endswith(".lua")]
    for f in files:
        text = git(repo, "show", "%s:%s" % (branch, f))
        ns = re.search(r'^\tNamespace\s*=\s*"([^"]+)"', text, re.M)
        is_widget = re.search(r'^\tType\s*=\s*"ScriptObject"', text, re.M)
        funcs = re.search(r"^\tFunctions\s*=\s*\n\t\{(.*?)^\t\},", text, re.M | re.S)
        if not funcs:
            continue
        for name in re.findall(r'^\t\t\tName\s*=\s*"([^"]+)"', funcs.group(1), re.M):
            if is_widget:
                doc_methods.add(name)
            elif ns:
                doc_ns.add(ns.group(1) + "." + name)
            else:
                doc_globals.add(name)
    return doc_globals, doc_ns, doc_methods


def lua_defined(repo, branch, name):
    out = subprocess.run(["git", "-C", repo, "grep", "-l", "-E", r"^function %s\s*\(|^%s\s*=\s*function" % (name, name),
                          branch, "--", "Interface/*.lua"], capture_output=True).stdout.decode()
    return out.split("\n")[0].replace(branch + ":", "") if out else ""


def used_by_blizzard(repo, branch, needle):
    if needle.startswith(":"):
        pattern = r"%s\s*\(" % re.escape(needle)
    else:
        pattern = r"(^|[^A-Za-z0-9_.:])%s\s*\(" % re.escape(needle)
    out = subprocess.run(["git", "-C", repo, "grep", "-c", "-E", pattern,
                          branch, "--", "Interface/*.lua", ":!Interface/AddOns/Blizzard_APIDocumentationGenerated"],
                         capture_output=True).stdout.decode()
    return sum(int(line.rsplit(":", 1)[1]) for line in out.splitlines() if line)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ui-source", required=True, help="git clone of Gethe/wow-ui-source")
    ap.add_argument("--branch", action="append", help="branch/ref to check (repeatable; first one decides the exit code)")
    ap.add_argument("file")
    a = ap.parse_args()
    branches = a.branch or ["origin/forever"]
    globals_, namespaced, methods = calls_in(a.file)
    idx = {b: index_branch(a.ui_source, b) for b in branches}
    missing_first = 0
    print("%-42s %s" % ("call", "  ".join("%-12s" % b.split("/")[-1] for b in branches)))
    rows = [("g", n) for n in globals_] + [("n", n) for n in namespaced] + [("m", n) for n in methods]
    for kind, name in rows:
        cells = []
        for b in branches:
            g, ns, me = idx[b]
            if kind == "g":
                if name in g:
                    st = "doc"
                elif lua_defined(a.ui_source, b, name):
                    st = "lua"
                elif used_by_blizzard(a.ui_source, b, name):
                    st = "used"
                else:
                    st = "MISSING"
            elif kind == "n":
                st = "doc" if name in ns else ("used" if used_by_blizzard(a.ui_source, b, name) else "MISSING")
            else:
                st = "doc" if name in me else ("used" if used_by_blizzard(a.ui_source, b, ":" + name) else "MISSING")
            if b == branches[0] and st == "MISSING":
                missing_first += 1
            cells.append("%-12s" % st)
        label = name if kind != "m" else ":" + name
        print("%-42s %s" % (label, "  ".join(cells)))
    print("%d call(s) checked; %d missing on %s" % (len(rows), missing_first, branches[0]))
    return 1 if missing_first else 0


if __name__ == "__main__":
    sys.exit(main())
