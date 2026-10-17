#!/usr/bin/env python3
"""check_paths.py - cross-platform path lint for World of Warcraft addon folders.

Finds path problems that Windows (NTFS) and default macOS (case-insensitive APFS)
hide, but that break on case-sensitive file systems (Linux CI, some Wine setups)
or produce broken paths in game:

  CASE     a TOC entry, XML <Script>/<Include> file, or a Lua/XML texture, font
           or sound path ("Interface\\AddOns\\<Addon>\\...") differs in case from
           the file or folder on disk
  MISSING  the referenced file does not exist at all
  SEP      wrong path separator for the context:
             - a single backslash inside a quoted Lua string ("Interface\\AddOns"
               must be written "Interface\\\\AddOns", "Interface/AddOns" or
               [[Interface\\AddOns]]); Lua treats "\\A", "\\t", "\\n"... as escapes
             - a doubled backslash in a TOC or XML file (no escaping is needed there)
             - absolute paths, drive letters or ".." components
  PREFIX   (warning) "Interface\\Addons" instead of the on-disk "Interface\\AddOns"
  EXT      (warning) a texture path names .blp but only .tga/.png exists (or the reverse);
           Questie has shipped such paths since 2024, so the client seems to tolerate it
  DUPCASE  two names in one folder differ only by case (they collide on Windows/macOS)
  WINNAME  name invalid on Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9, <>:"|?*,
           trailing dot or space)
  TOCNAME  folder name and TOC base name differ (the client only loads <Folder>/<Folder>.toc)
  BOM      (warning) UTF-8 byte-order mark at the start of a .toc file
  LONG     (warning) path longer than 259 characters under a long Windows install prefix

Usage:
  python3 check_paths.py [options] PATH [PATH ...]

PATH is an addon folder (contains <Name>.toc or <Name>_<Flavor>.toc) or a folder whose
sub-folders are addons (a multi-addon repository). Only files loaded through the TOC
files (and the XML files they include) are scanned for media paths unless --all-files.

Options:
  --all-files       scan every .lua/.xml file for media paths, not only loaded ones
  --exclude GLOB    skip files/folders matching GLOB (repeatable; .pkgmeta "ignore" is
                    honoured automatically)
  --prefix-len N    install prefix length for the LONG check (default 73:
                    C:\\Program Files (x86)\\World of Warcraft\\_classic_beta_\\Interface\\AddOns\\)
  --strict          exit 1 on warnings too
  -q, --quiet       only print the summary line

Exit status: 0 = no errors, 1 = errors (or warnings with --strict), 2 = usage error.
Standard library only; Python 3.8+.
"""
import fnmatch
import os
import re
import sys

VERSION = "1.0.0"
# Microsoft "Naming Files, Paths, and Namespaces" also reserves COM/LPT with superscript 1-3
RESERVED = ({"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}
            | {p + c for p in ("COM", "LPT") for c in ("\u00b9", "\u00b2", "\u00b3")})
BAD_CHARS = set('<>:"|?*')
DEFAULT_PREFIX = len("C:\\Program Files (x86)\\World of Warcraft\\_classic_beta_\\Interface\\AddOns\\")
SKIP_DIRS = {".git", ".github", ".release", ".svn", ".hg", "node_modules", ".vscode", ".idea"}
TOC_SUFFIX = re.compile(r"[-_](Mainline|Standard|Classic|Vanilla|TBC|BCC|Wrath|WOTLKC|Cata|Mists|Camelot|Forever)$", re.I)
TOC_COND = re.compile(r"\s*\[(?:AllowLoad|ExcludeLoad)[A-Za-z]*\s[^\]]*\]")
TOC_VAR = re.compile(r"\[(Family|Game|TextLocale)\]", re.I)
XML_TAG = re.compile(r"<\s*([A-Za-z_][\w.:-]*)([^<>]*?)/?\s*>", re.S)
XML_ATTR = re.compile(r"([A-Za-z_][\w.:-]*)\s*=\s*(\"([^\"]*)\"|'([^']*)')", re.S)
# Interface\AddOns\<Addon>\rest - separators may be \ \\ or /
MEDIA = re.compile(r"(?i:interface)((?:\\|/)+)((?i:addons))((?:\\|/)+)([^\\/:|\"'%\s]+)((?:(?:\\|/)+[^\\/:|\"'%\r\n\t]*)*)")
TEXTURE_EXTS = ("", ".blp", ".tga", ".png", ".jpg", ".jpeg")
LONG_OPEN = re.compile(r"\[(=*)\[")
LUA_ESCAPES = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
               "\\": "\\", '"': '"', "'": "'", "\n": "\n"}


class Finding:
    __slots__ = ("level", "code", "where", "msg")

    def __init__(self, level, code, where, msg):
        self.level, self.code, self.where, self.msg = level, code, where, msg

    def __str__(self):
        return "%-5s %-7s %s: %s" % (self.level, self.code, self.where, self.msg)


# --------------------------------------------------------------------- tree index
class Tree:
    """Exact-case directory listings below one root (paths use '/')."""

    def __init__(self, root, excludes):
        self.root = root
        self.dirs = {}  # rel dir -> {name: is_dir}
        self.files = []  # rel file paths
        self.excludes = excludes
        for dp, dns, fns in os.walk(root):
            rel = os.path.relpath(dp, root).replace(os.sep, "/")
            rel = "" if rel == "." else rel
            dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and not self.excluded(join(rel, d)))
            fns = sorted(f for f in fns if not self.excluded(join(rel, f)))
            self.dirs[rel] = {d: True for d in dns}
            self.dirs[rel].update({f: False for f in fns})
            self.files.extend(join(rel, f) for f in fns)

    def excluded(self, rel):
        return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel.split("/")[-1], g) for g in self.excludes)

    def resolve(self, parts, want_dir=None):
        """Walk components. Returns (status, on_disk_rel): status in exact|case|missing."""
        cur, out, status = "", [], "exact"
        for i, p in enumerate(parts):
            listing = self.dirs.get(cur)
            if listing is None:
                return "missing", None
            if p in listing:
                name = p
            else:
                hits = [n for n in listing if n.lower() == p.lower()]
                if not hits:
                    return "missing", None
                name, status = hits[0], "case"
            last = i == len(parts) - 1
            if not last and not listing[name]:
                return "missing", None
            if last and want_dir is not None and listing[name] != want_dir:
                return "missing", None
            out.append(name)
            cur = join(cur, name)
        return status, "/".join(out)


def join(a, b):
    return b if not a else a + "/" + b


def norm_parts(path):
    return [p for p in re.split(r"[\\/]+", path) if p not in ("", ".")]


def collapse(parts):
    """Resolve ".." components; None when the path climbs above the addon folder."""
    out = []
    for p in parts:
        if p == "..":
            if not out:
                return None
            out.pop()
        else:
            out.append(p)
    return out


# ----------------------------------------------------------------------- Lua lexer
def lua_strings(src):
    """Yield (kind, raw, line, end) for Lua string literals; kind is 'short' or 'long'.
    Comments are skipped. raw is the source text between the delimiters."""
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
        elif src.startswith("--", i):
            m = LONG_OPEN.match(src, i + 2)
            if m:
                end = src.find("]" + m.group(1) + "]", m.end())
                end = n if end < 0 else end + len(m.group(1)) + 2
            else:
                end = src.find("\n", i)
                end = n if end < 0 else end
            line += src.count("\n", i, end)
            i = end
        elif c == "[" and LONG_OPEN.match(src, i):
            m = LONG_OPEN.match(src, i)
            close = "]" + m.group(1) + "]"
            end = src.find(close, m.end())
            end = n if end < 0 else end
            yield "long", src[m.end():end], line, end + len(close)
            line += src.count("\n", i, end)
            i = end + len(close)
        elif c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            raw = src[i + 1:min(j, n)]
            yield "short", raw, line, j + 1
            line += raw.count("\n")
            i = j + 1
        else:
            i += 1


def lua_decode(raw):
    """Runtime value of a Lua 5.1 short string (unknown escapes drop the backslash)."""
    out, i = [], 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nx = raw[i + 1]
            m = re.match(r"\d{1,3}", raw[i + 1:])
            if m:
                out.append(chr(int(m.group(0)) % 256))
                i += 1 + len(m.group(0))
                continue
            out.append(LUA_ESCAPES.get(nx, nx))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


# ------------------------------------------------------------------- the checker
class Checker:
    def __init__(self, opts):
        self.opts = opts
        self.findings = []
        self.addons = {}  # name -> (folder abs path, Tree, toc files)
        self.external = 0
        self.refs = 0
        self.provided = 0  # missing paths covered by .pkgmeta externals
        self.root_externals = []  # from a .pkgmeta next to the addon folders (multi-addon repo)

    def add(self, level, code, where, msg):
        self.findings.append(Finding(level, code, where, msg))

    # ---- discovery
    def discover(self, path):
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            raise SystemExit("error: not a directory: %s" % path)
        if self.add_addon(path):
            return
        self.root_externals += pkgmeta_externals(path)
        found = False
        for d in sorted(os.listdir(path)):
            sub = os.path.join(path, d)
            if d in SKIP_DIRS or d.startswith(".") or not os.path.isdir(sub):
                continue
            if any(f.lower().endswith(".toc") for f in os.listdir(sub)):
                found = self.add_addon(sub) or found
        if not found:
            raise SystemExit("error: no addon folder (with a .toc) in %s" % path)

    def add_addon(self, folder):
        tocs = sorted(f for f in os.listdir(folder) if f.lower().endswith(".toc") and os.path.isfile(os.path.join(folder, f)))
        if not tocs:
            return False
        dirname = os.path.basename(folder)
        bases = sorted({TOC_SUFFIX.sub("", f[:-4]) for f in tocs})
        exact = [b for b in bases if b == dirname]
        if exact:
            name = dirname
        else:
            name = bases[0] if len(bases) == 1 else dirname
            ci = [b for b in bases if b.lower() == dirname.lower()]
            if ci:
                self.add("ERROR", "TOCNAME", "%s/%s.toc" % (dirname, ci[0]),
                         'TOC base name "%s" differs in case from folder "%s"' % (ci[0], dirname))
                name = dirname
            elif len(bases) == 1:
                self.add("WARN", "TOCNAME", dirname,
                         'folder "%s" holds %s.toc - it must be installed as Interface/AddOns/%s' % (dirname, bases[0], bases[0]))
        excludes = list(self.opts["exclude"]) + pkgmeta_ignores(folder)
        self.addons[name] = (folder, Tree(folder, excludes), tocs, pkgmeta_externals(folder))
        return True

    # ---- reference resolution
    def check_ref(self, addon, where, parts, kind, media=False, want_dir=None):
        self.refs += 1
        folder, tree, _, externals = self.addons[addon]
        exts = TEXTURE_EXTS if media and "." not in (parts[-1] if parts else "") else ("",)
        best = None
        for e in exts:
            p = parts[:-1] + [parts[-1] + e] if parts else parts
            status, disk = tree.resolve(p, want_dir)
            if status == "exact":
                return
            if status == "case" and best is None:
                best = disk
        shown = "/".join(parts)
        if best:
            self.add("ERROR", "CASE", where, '%s "%s" -> on disk "%s"' % (kind, shown, best))
            return
        stem, ext = os.path.splitext(parts[-1]) if parts else ("", "")
        if media and ext.lower() in TEXTURE_EXTS[1:]:
            for e in TEXTURE_EXTS[1:]:
                status, disk = tree.resolve(parts[:-1] + [stem + e], want_dir)
                if status != "missing":
                    level, code = ("WARN", "EXT") if status == "exact" else ("ERROR", "CASE")
                    self.add(level, code, where, '%s "%s" -> only "%s" exists (give the real extension, or none)' % (kind, shown, disk))
                    return
        rel = "/".join(parts).lower()
        cands = (rel + "/", addon.lower() + "/" + rel + "/")  # .pkgmeta keys may include the addon folder
        if any(c.startswith(x.lower().rstrip("/") + "/") for x in list(externals) + self.root_externals for c in cands):
            self.provided += 1
            return  # fetched at package time by .pkgmeta externals
        self.add("ERROR", "MISSING", where, '%s "%s" not found in %s/' % (kind, shown, addon))

    def check_media(self, where, text, context, scan_addon):
        """text = path text as the author intended (separators normalised to \\ or /)."""
        for m in MEDIA.finditer(text):
            self.check_media_match(where, m, context, scan_addon)

    def check_media_match(self, where, m, context, scan_addon, partial=False):
        seps = [m.group(1), m.group(3)] + re.findall(r"[\\/]+", m.group(5))
        if context in ("toc", "xml", "lua-long") and any("\\\\" in s for s in seps):
            self.add("WARN", "SEP", where, 'doubled backslash in "%s" (escaping is only needed inside quoted Lua strings)' % m.group(0))
        if m.group(2) != "AddOns":
            self.add("WARN", "PREFIX", where, '"Interface%s%s" - the folder on disk is "AddOns" (case-sensitive file systems)' % (m.group(1), m.group(2)))
        name = m.group(4)
        target = self.addons.get(name)
        if target is None:
            ci = [a for a in self.addons if a.lower() == name.lower()]
            if not ci:
                self.external += 1
                return
            self.add("ERROR", "CASE", where, 'addon folder written "%s", on disk "%s"' % (name, ci[0]))
            name = ci[0]
        rest = m.group(5)
        parts = norm_parts(rest)
        if not parts:
            return
        is_dir_prefix = bool(re.search(r"[\\/]$", rest))
        if partial and not is_dir_prefix:
            self.check_prefix(name, where, parts)
            return
        self.check_ref(name, where, parts, "media path", media=not is_dir_prefix, want_dir=True if is_dir_prefix else None)

    def check_prefix(self, addon, where, parts):
        """Literal is concatenated with more text: its last component is a name prefix."""
        self.refs += 1
        tree = self.addons[addon][1]
        status, disk = tree.resolve(parts[:-1], want_dir=True) if len(parts) > 1 else ("exact", "")
        if status == "missing":
            self.add("ERROR", "MISSING", where, 'media folder "%s" not found in %s/' % ("/".join(parts[:-1]), addon))
            return
        names = tree.dirs.get(disk, {})
        if any(n.startswith(parts[-1]) for n in names):
            if status == "case":
                self.add("ERROR", "CASE", where, 'media folder "%s" -> on disk "%s"' % ("/".join(parts[:-1]), disk))
            return
        hits = [n for n in names if n.lower().startswith(parts[-1].lower())]
        if hits:
            self.add("ERROR", "CASE", where, 'file-name prefix "%s" -> on disk "%s"' % ("/".join(parts), join(disk, hits[0])))
        else:
            self.add("ERROR", "MISSING", where, 'no file starting with "%s" in %s/' % ("/".join(parts), addon))

    def check_sep(self, where, value, context):
        if re.match(r"^[A-Za-z]:[\\/]|^[\\/]", value):
            self.add("ERROR", "SEP", where, '"%s" is an absolute path - use a path relative to the addon folder' % value)
            return False
        if context in ("toc", "xml") and "\\\\" in value:
            self.add("WARN", "SEP", where, 'doubled backslash in "%s" (escaping is only needed inside quoted Lua strings)' % value)
        return True

    # ---- per-file scanners
    def scan_toc(self, addon, toc, loaded):
        folder, tree, _, _ = self.addons[addon]
        raw = open(os.path.join(folder, toc), "rb").read()
        where0 = "%s/%s" % (addon, toc)
        if raw.startswith(b"\xef\xbb\xbf"):
            self.add("WARN", "BOM", where0, "UTF-8 BOM before the first line (save as UTF-8 without BOM)")
        for no, line in enumerate(raw.decode("utf-8", "replace").lstrip("\ufeff").splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            s = TOC_COND.sub("", s).strip()
            where = "%s:%d" % (where0, no)
            if not self.check_sep(where, s, "toc"):
                continue
            if TOC_VAR.search(s):
                self.check_variable_entry(addon, where, s, loaded)
                continue
            parts = collapse(norm_parts(s))
            if parts is None:
                self.add("ERROR", "SEP", where, '"%s" climbs out of the addon folder with ".."' % s)
                continue
            if not parts:
                continue
            self.check_ref(addon, where, parts, "TOC entry")
            status, disk = tree.resolve(parts)
            if disk:
                loaded.add(disk)

    def check_variable_entry(self, addon, where, entry, loaded):
        """[Family]/[Game]/[TextLocale] are filled in by the client: need >= 1 match."""
        tree = self.addons[addon][1]
        pieces = TOC_VAR.split("/".join(norm_parts(entry)))  # literal text at even indexes
        rx = "^" + "[^/]+".join(re.escape(x) for x in pieces[::2]) + "$"
        exact = [f for f in tree.files if re.match(rx, f)]
        if exact:
            loaded.update(exact)
            return
        ci = [f for f in tree.files if re.match(rx, f, re.I)]
        if ci:
            self.add("ERROR", "CASE", where, 'TOC entry "%s" matches only "%s" ignoring case' % (entry, ci[0]))
            loaded.update(ci)
        else:
            self.add("WARN", "MISSING", where, 'TOC entry "%s" matches no file for any [Family]/[Game]/[TextLocale]' % entry)

    def scan_xml(self, addon, rel, loaded, queue):
        folder, tree, _, _ = self.addons[addon]
        text = open(os.path.join(folder, rel), "rb").read().decode("utf-8", "replace")
        text_nc = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
        base = norm_parts(os.path.dirname(rel))
        for tm in XML_TAG.finditer(text_nc):
            tag = tm.group(1).split(":")[-1]
            line = text_nc.count("\n", 0, tm.start()) + 1
            where = "%s/%s:%d" % (addon, rel, line)
            for am in XML_ATTR.finditer(tm.group(2)):
                attr, val = am.group(1), am.group(3) if am.group(3) is not None else am.group(4)
                if tag in ("Script", "Include") and attr == "file":
                    if not self.check_sep(where, val, "xml"):
                        continue
                    if MEDIA.match(val):
                        self.check_media(where, val, "xml", addon)
                        continue
                    parts = collapse(base + norm_parts(val))
                    if parts is None:
                        self.add("ERROR", "SEP", where, '"%s" climbs out of the addon folder with ".."' % val)
                        continue
                    self.check_ref(addon, where, parts, "<%s file>" % tag)
                    status, disk = tree.resolve(parts)
                    if disk and disk not in loaded:
                        loaded.add(disk)
                        if disk.lower().endswith(".xml"):
                            queue.append(disk)
                elif MEDIA.search(val):
                    self.check_media(where, val, "xml", addon)
        # Lua inside element text (<OnLoad>, <Binding>, inline <Script>): blank out tags,
        # keep line numbers, undo the XML entities, then scan it like a Lua file
        code = XML_TAG.sub(lambda m: "\n" * m.group(0).count("\n"), text_nc)
        for ent, ch in (("&quot;", '"'), ("&apos;", "'"), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
            code = code.replace(ent, ch)
        if re.search(r"(?i)interface", code):
            self.scan_lua_source(addon, rel, code)

    def scan_lua(self, addon, rel):
        folder, _, _, _ = self.addons[addon]
        src = open(os.path.join(folder, rel), "rb").read().decode("utf-8", "replace")
        self.scan_lua_source(addon, rel, src)

    def scan_lua_source(self, addon, rel, src):
        for kind, raw, line, end in lua_strings(src):
            if not re.search(r"(?i)interface", raw):
                continue
            where = "%s/%s:%d" % (addon, rel, line)
            # "...\\bullet" .. n  -> the last component is only a file-name prefix
            partial = re.match(r"\s*\.\.", src[end:end + 40]) is not None
            if kind == "long":
                for m in MEDIA.finditer(raw):
                    self.check_media_match(where, m, "lua-long", addon, partial)
                continue
            # In the source text of a quoted Lua string a separator must be \\ (an escaped
            # backslash) or /. A run of an odd number of backslashes means one of them
            # escapes the next character (\A becomes "A", \t becomes a TAB).
            flagged = False
            for m in MEDIA.finditer(raw):
                runs = [m.group(1), m.group(3)] + re.findall(r"[\\/]+", m.group(5))
                odd = any(len(r.replace("/", "")) % 2 == 1 for r in runs)
                if odd and not flagged:
                    flagged = True
                    self.add("ERROR", "SEP", where,
                             'single backslash in a quoted Lua string: "%s" is read by Lua as %r - write \\\\ or / (or use [[...]])'
                             % (clip(raw, 90), clip(lua_decode(raw), 70)))
                self.check_media_match(where, m, "lua", addon, partial)

    # ---- names
    def check_names(self, addon):
        folder, tree, _, _ = self.addons[addon]
        for d, listing in tree.dirs.items():
            seen = {}
            for name in listing:
                low = name.lower()
                if low in seen:
                    self.add("ERROR", "DUPCASE", "%s/%s" % (addon, join(d, name)),
                             'differs only by case from "%s" - one of them is lost on Windows/macOS' % join(d, seen[low]))
                seen[low] = name
                stem = name.split(".")[0].upper()
                if stem in RESERVED or any(c in BAD_CHARS for c in name) or name.endswith((".", " ")):
                    self.add("ERROR", "WINNAME", "%s/%s" % (addon, join(d, name)), "not a valid Windows file name")
        for f in tree.files:
            total = self.opts["prefix_len"] + len(addon) + 1 + len(f)
            if total > 259:
                self.add("WARN", "LONG", "%s/%s" % (addon, f),
                         "%d characters with a %d-character install prefix (Windows MAX_PATH is 260)" % (total, self.opts["prefix_len"]))

    def run(self):
        for addon in sorted(self.addons):
            folder, tree, tocs, _ = self.addons[addon]
            self.check_names(addon)
            loaded = set()
            for toc in tocs:
                self.scan_toc(addon, toc, loaded)
            if tree.resolve(["Bindings.xml"])[0] == "exact":  # loaded by the client without a TOC entry
                loaded.add("Bindings.xml")
            queue = sorted(f for f in loaded if f.lower().endswith(".xml"))
            seen_xml = set()
            while queue:
                rel = queue.pop()
                if rel in seen_xml or not os.path.isfile(os.path.join(folder, rel)):
                    continue
                seen_xml.add(rel)
                self.scan_xml(addon, rel, loaded, queue)
            targets = tree.files if self.opts["all_files"] else sorted(loaded)
            for rel in targets:
                low = rel.lower()
                if low.endswith(".lua"):
                    self.scan_lua(addon, rel)
                elif low.endswith(".xml") and self.opts["all_files"] and rel not in seen_xml:
                    self.scan_xml(addon, rel, set(), [])


def clip(text, n):
    return text if len(text) <= n else text[:n - 3] + "..."


def pkgmeta_section(folder, key):
    """Tiny .pkgmeta reader: list items / mapping keys under a top-level key."""
    for name in (".pkgmeta", "pkgmeta.yaml", "pkgmeta.yml"):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            break
    else:
        return []
    out, inside = [], False
    for line in open(p, encoding="utf-8", errors="replace"):
        if re.match(r"^\S", line):
            inside = line.split(":")[0].strip() == key
            continue
        if not inside:
            continue
        m = re.match(r"^\s+-\s+(.+?)\s*$", line) or re.match(r"^\s{2}([^\s#][^:]*):", line)
        if m:
            out.append(m.group(1).strip().strip("\"'"))
    return out


def pkgmeta_ignores(folder):
    return [g.rstrip("/") for g in pkgmeta_section(folder, "ignore")]


def pkgmeta_externals(folder):
    return pkgmeta_section(folder, "externals")


def main(argv):
    opts = {"all_files": False, "exclude": [], "prefix_len": DEFAULT_PREFIX, "strict": False, "quiet": False}
    paths, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--all-files":
            opts["all_files"] = True
        elif a == "--exclude" and i + 1 < len(argv):
            opts["exclude"].append(argv[i + 1])
            i += 1
        elif a == "--prefix-len" and i + 1 < len(argv):
            opts["prefix_len"] = int(argv[i + 1])
            i += 1
        elif a == "--strict":
            opts["strict"] = True
        elif a in ("-q", "--quiet"):
            opts["quiet"] = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        elif a == "--version":
            print("check_paths.py " + VERSION)
            return 0
        elif a.startswith("-"):
            print("error: unknown option " + a, file=sys.stderr)
            return 2
        else:
            paths.append(a)
        i += 1
    if not paths:
        print(__doc__, file=sys.stderr)
        return 2
    chk = Checker(opts)
    for p in paths:
        chk.discover(p)
    chk.run()
    errors = [f for f in chk.findings if f.level == "ERROR"]
    warns = [f for f in chk.findings if f.level == "WARN"]
    if not opts["quiet"]:
        def order(f):
            file_part, _, line = f.where.partition(":")
            return (file_part, int(line) if line.isdigit() else 0, f.code)
        for f in sorted(chk.findings, key=order):
            print(f)
    counts = {}
    for f in chk.findings:
        counts[f.code] = counts.get(f.code, 0) + 1
    detail = ", ".join("%s %d" % (k, v) for k, v in sorted(counts.items()))
    print("%d addon folder(s), %d path reference(s) checked (%d into other addons not scanned, %d left to .pkgmeta externals):"
          " %d error(s), %d warning(s)%s"
          % (len(chk.addons), chk.refs, chk.external, chk.provided, len(errors), len(warns), " [" + detail + "]" if detail else ""))
    return 1 if errors or (opts["strict"] and warns) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
