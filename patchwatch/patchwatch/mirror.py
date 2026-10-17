"""Access to the Gethe/wow-ui-source mirror through git.

The cache is a *bare, blobless* clone (``--filter=blob:none``) holding only
the branches you watch.  Commits and trees for the full history of the seven
default branches take under 10 MB; file contents (blobs) are fetched on
demand, in one batch per build, only for the folders patchwatch reads.

How the mirror records builds (checked on the real mirror, 2026-10-16):

* every export is one commit whose subject is ``"<version> (<build>)"``,
  e.g. ``"1.60.1 (70425)"`` or ``"12.1.5 (70391)"``;
* the root file ``version.txt`` holds ``"<version>.<build>"``;
* lightweight tags named after versions (``12.1.0``) exist, but they mark the
  last export of that version on *any* branch (often ptr), so patchwatch does
  not use them to find live builds;
* commit dates are the export time, which is close to the build's release
  on that branch.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

DEFAULT_URL = "https://github.com/Gethe/wow-ui-source"
DEFAULT_BRANCHES = ["forever", "live", "ptr", "beta", "classic_era", "classic", "classic_anniversary"]

_SUBJECT_RE = re.compile(r"^\s*(\d+)\.(\d+)\.(\d+)\s*\((\d+)\)")
_VERSION_TXT_RE = re.compile(r"^\s*(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?")


class MirrorError(RuntimeError):
    pass


class NotEnoughBuilds(MirrorError):
    """A build spec such as ``live@-1`` or ``live@2025-01-01`` asks for a build the branch does not have yet."""


def interface_number(version: str) -> Optional[int]:
    """'12.1.5' -> 120105, '1.60.1' -> 16001, '1.15.9' -> 11509."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", version or "")
    if not m:
        return None
    a, b, c = (int(x) for x in m.groups())
    return a * 10000 + b * 100 + c


def default_cache_dir() -> Path:
    """Per-user cache folder for macOS, Windows and Linux (override with PATCHWATCH_CACHE_DIR)."""
    env = os.environ.get("PATCHWATCH_CACHE_DIR")
    if env:
        return Path(env).expanduser()
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "patchwatch" / "Cache"
        return Path.home() / "AppData" / "Local" / "patchwatch" / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "patchwatch"
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base) if base else Path.home() / ".cache") / "patchwatch"


@dataclass
class Build:
    branch: Optional[str]
    commit: str
    date: str  # ISO-8601 UTC
    version: Optional[str]
    build: Optional[int]
    subject: str = ""
    files_changed: Optional[int] = None
    api_doc_files_changed: Optional[int] = None

    @property
    def interface(self) -> Optional[int]:
        return interface_number(self.version or "")

    @property
    def label(self) -> str:
        if self.version and self.build:
            return f"{self.version}.{self.build}"
        if self.version:
            return self.version
        # dir: sources without a version.txt: the whole path, not its first 9 characters
        return self.commit if self.commit.startswith("dir:") else self.commit[:9]

    def to_json(self) -> Dict[str, object]:
        d = asdict(self)
        d["interface"] = self.interface
        d["label"] = self.label
        return d


def _utc(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return iso


def parse_subject(subject: str):
    m = _SUBJECT_RE.match(subject or "")
    if not m:
        return None, None
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}", int(m.group(4))


def parse_version_txt(text: str):
    m = _VERSION_TXT_RE.match(text or "")
    if not m:
        return None, None
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}", (int(m.group(4)) if m.group(4) else None)


class Mirror:
    """A bare, partial clone of the mirror in ``path``."""

    def __init__(self, path: Path, url: str = DEFAULT_URL, git: str = "git",
                 offline: bool = False, verbose: bool = False) -> None:
        self.path = Path(path)
        self.url = url
        self.git_exe = git
        self.offline = offline
        self.verbose = verbose

    # -- git plumbing ---------------------------------------------------
    def _env(self) -> Dict[str, str]:
        env = dict(os.environ)
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        env["LC_ALL"] = "C"
        if self.offline:
            env["GIT_NO_LAZY_FETCH"] = "1"  # git >= 2.44 honours this
        return env

    def git(self, *args: str, input_bytes: Optional[bytes] = None, check: bool = True,
            binary: bool = False):
        cmd = [self.git_exe, "--git-dir", str(self.path)] + list(args)
        if self.verbose:
            print("+ " + " ".join(cmd), file=sys.stderr)
        try:
            proc = subprocess.run(cmd, input=input_bytes, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=self._env())
        except FileNotFoundError as exc:
            raise MirrorError(f"git executable not found ({self.git_exe}); install Git and put it on PATH") from exc
        if check and proc.returncode != 0:
            raise MirrorError(f"git {' '.join(args[:3])} failed ({proc.returncode}): "
                              f"{proc.stderr.decode('utf-8', 'replace').strip()}")
        if binary:
            return proc
        return proc.stdout.decode("utf-8", "replace")

    def exists(self) -> bool:
        return (self.path / "HEAD").is_file() and (self.path / "objects").is_dir()

    def init(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        if not self.exists():
            subprocess.run([self.git_exe, "init", "--bare", "-q", str(self.path)], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self._env())
        cur = self.git("config", "--get", "remote.origin.url", check=False).strip()
        if not cur:
            self.git("config", "remote.origin.url", self.url)
        elif cur != self.url:
            self.git("config", "remote.origin.url", self.url)
        self.git("config", "remote.origin.promisor", "true")
        self.git("config", "remote.origin.partialclonefilter", "blob:none")
        self.git("config", "core.logAllRefUpdates", "false")
        self.git("config", "gc.auto", "0")

    def configured_branches(self) -> List[str]:
        out = self.git("config", "--get-all", "remote.origin.fetch", check=False)
        res = []
        for line in out.splitlines():
            m = re.match(r"^\+?refs/heads/([^:]+):", line.strip())
            if m:
                res.append(m.group(1))
        return res

    def remote_branches(self) -> List[str]:
        """Branch names the mirror has now (``git ls-remote --heads``; one small network request)."""
        self.init()
        out = self.git("ls-remote", "--heads", "origin")
        names = []
        for line in out.splitlines():
            _, _, ref = line.partition("\t")
            if ref.startswith("refs/heads/"):
                names.append(ref[len("refs/heads/"):])
        return sorted(names)

    def fetch(self, branches: Sequence[str], tags: bool = False, skip_missing: bool = False) -> List[str]:
        """Create or update the cache for ``branches`` (commits and trees only, no file contents).

        Other branches already in the cache are kept but not updated.  With ``skip_missing``, the
        branches the mirror does not have are left out instead of failing the whole fetch, and
        returned (needs the network; offline it returns nothing).
        """
        self.init()
        missing: List[str] = []
        if skip_missing and not self.offline and branches:
            remote = set(self.remote_branches())
            missing = [b for b in branches if b not in remote]
            branches = [b for b in branches if b in remote]
        known = self.configured_branches()
        for b in branches:
            if b not in known:
                self.git("config", "--add", "remote.origin.fetch", f"+refs/heads/{b}:refs/remotes/origin/{b}")
        if self.offline or (not branches and not tags):
            return missing
        args = ["fetch", "--filter=blob:none", "--quiet", "--tags" if tags else "--no-tags", "origin"]
        args += [f"+refs/heads/{b}:refs/remotes/origin/{b}" for b in branches]
        self.git(*args)
        return missing

    def has_branch(self, branch: str) -> bool:
        return bool(self.git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}^{{commit}}",
                             check=False).strip())

    def branch_ref(self, branch: str) -> str:
        if self.has_branch(branch):
            return f"refs/remotes/origin/{branch}"
        if self.git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}", check=False).strip():
            return f"refs/heads/{branch}"
        raise MirrorError(f"branch {branch!r} is not in the cache; run 'patchwatch fetch --branches {branch}'")

    # -- builds ---------------------------------------------------------
    def builds(self, branch: str, with_files: bool = False, after: Optional[str] = None) -> List[Build]:
        """Builds on ``branch``, oldest first.  ``after`` limits to commits after that commit."""
        ref = self.branch_ref(branch)
        rng = f"{after}..{ref}" if after else ref
        out = self.git("log", "--first-parent", "--format=%H%x1f%cI%x1f%s", rng)
        result: List[Build] = []
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 3:
                continue
            sha, date, subject = parts[0], parts[1], parts[2]
            version, build = parse_subject(subject)
            if version is None:
                continue  # e.g. "Initial commit" or automation edits
            result.append(Build(branch, sha, _utc(date), version, build, subject))
        result.reverse()
        if with_files:
            counts = self.changed_file_counts(rng)
            for b in result:
                b.files_changed, b.api_doc_files_changed = counts.get(b.commit, (0, 0))
        return result

    def changed_file_counts(self, rng: str) -> Dict[str, tuple]:
        """{commit: (files changed, API doc files changed)} using trees only (no blobs)."""
        from .apidocs import DOC_DIR
        out = self.git("log", "--first-parent", "--format=@@%H", "--name-only", "--no-renames", rng)
        counts: Dict[str, List[int]] = {}
        cur = None
        for line in out.splitlines():
            if line.startswith("@@"):
                cur = line[2:].strip()
                counts[cur] = [0, 0]
            elif line.strip() and cur:
                counts[cur][0] += 1
                if line.startswith(DOC_DIR + "/"):
                    counts[cur][1] += 1
        return {k: tuple(v) for k, v in counts.items()}

    def commit_info(self, rev: str, branch: Optional[str] = None) -> Build:
        out = self.git("log", "-1", "--format=%H%x1f%cI%x1f%s", rev, "--").strip()
        if not out:
            raise MirrorError(f"unknown revision {rev!r}")
        sha, date, subject = out.split("\x1f", 2)
        version, build = parse_subject(subject)
        if version is None:
            v2, b2 = parse_version_txt(self.read_text(sha, "version.txt") or "")
            version, build = v2, b2
        return Build(branch, sha, _utc(date), version, build, subject)

    def resolve(self, spec: str) -> Build:
        """Resolve a build spec.

        * ``forever`` / ``forever@latest`` - newest build on the branch
        * ``forever@first`` - oldest build on the branch
        * ``forever@-1`` - the build before the newest (``-N`` = N builds back)
        * ``live@12.1.0`` - newest build of that version on the branch
        * ``forever@69876`` or ``forever@1.60.1.69876`` - newest commit of that build
        * ``live@2026-08-20`` - newest build on or before that date (UTC)
        * ``tag:12.1.0`` - a mirror tag; ``<sha>`` - any commit
        """
        spec = spec.strip()
        if spec.startswith("tag:"):
            return self.commit_info(f"refs/tags/{spec[4:]}^{{commit}}")
        branch, _, sel = spec.partition("@")
        if not self._looks_like_branch(branch):
            return self.commit_info(spec)
        builds = self.builds(branch)
        if not builds:
            raise MirrorError(f"no builds found on branch {branch!r}")
        sel = sel or "latest"
        if sel == "latest":
            return builds[-1]
        if sel == "first":
            return builds[0]
        if re.fullmatch(r"-\d+", sel):
            n = int(sel[1:])
            if n >= len(builds):
                raise NotEnoughBuilds(f"{spec}: only {len(builds)} builds on {branch}")
            return builds[-1 - n]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", sel):
            cands = [b for b in builds if b.date[:10] <= sel]
            if not cands:
                raise NotEnoughBuilds(f"{spec}: no build on or before {sel}")
            return cands[-1]
        if re.fullmatch(r"\d+", sel):
            cands = [b for b in builds if b.build == int(sel)]
        elif re.fullmatch(r"\d+\.\d+\.\d+\.\d+", sel):
            v, _, bn = sel.rpartition(".")
            cands = [b for b in builds if b.version == v and b.build == int(bn)]
        elif re.fullmatch(r"\d+\.\d+\.\d+", sel):
            cands = [b for b in builds if b.version == sel]
        else:
            raise MirrorError(f"cannot understand build selector {sel!r} in {spec!r}")
        if not cands:
            raise MirrorError(f"no build matching {spec!r}")
        return cands[-1]

    def _looks_like_branch(self, name: str) -> bool:
        if not name:
            return False
        if self.has_branch(name):
            return True
        if re.fullmatch(r"[0-9a-f]{7,40}", name):
            return False
        try:
            self.branch_ref(name)
            return True
        except MirrorError:
            return False

    # -- file access ----------------------------------------------------
    def list_tree(self, commit: str, prefix: str) -> List[tuple]:
        """[(path, blob_oid)] under ``prefix`` at ``commit`` (trees only, no blob fetch)."""
        out = self.git("ls-tree", "-r", "--full-tree", commit, "--", prefix.rstrip("/") + "/")
        res = []
        for line in out.splitlines():
            meta, _, path = line.partition("\t")
            parts = meta.split()
            if len(parts) == 3 and parts[1] == "blob":
                res.append((path, parts[2]))
        return res

    def is_partial(self) -> bool:
        return self.git("config", "--get", "remote.origin.promisor", check=False).strip() == "true"

    def prefetch(self, oids: Iterable[str]) -> None:
        """Fetch many missing blobs in one request instead of one round trip per file."""
        oids = sorted(set(oids))
        if not oids or self.offline or not self.is_partial():
            return
        # Same request git's own lazy fetch makes, but for all objects at once.
        # git skips the network when every object is already present
        # (checking first with cat-file would itself trigger lazy fetches).
        proc = self.git("-c", "fetch.negotiationAlgorithm=noop", "fetch", "origin", "--no-tags",
                        "--no-write-fetch-head", "--recurse-submodules=no", "--filter=blob:none",
                        "--stdin", input_bytes=("\n".join(oids) + "\n").encode(), check=False, binary=True)
        if proc.returncode != 0 and self.verbose:
            print("batch prefetch failed; falling back to lazy fetch: "
                  + proc.stderr.decode("utf-8", "replace"), file=sys.stderr)

    def read_blobs(self, oids: Sequence[str]) -> Dict[str, bytes]:
        if not oids:
            return {}
        self.prefetch(oids)
        proc = self.git("cat-file", "--batch", input_bytes=("\n".join(oids) + "\n").encode(),
                        binary=True)
        data = proc.stdout
        out: Dict[str, bytes] = {}
        pos = 0
        for oid in oids:
            nl = data.index(b"\n", pos)
            header = data[pos:nl].decode("ascii", "replace").split()
            pos = nl + 1
            if len(header) < 3 or header[1] == "missing":
                continue
            size = int(header[2])
            out[oid] = data[pos:pos + size]
            pos += size + 1  # trailing newline
        return out

    def read_dir(self, commit: str, prefix: str, suffixes: Sequence[str] = (".lua",)) -> Dict[str, str]:
        """{path relative to prefix: text} for files under ``prefix`` at ``commit``."""
        entries = [(p, o) for p, o in self.list_tree(commit, prefix)
                   if not suffixes or p.lower().endswith(tuple(suffixes))]
        blobs = self.read_blobs([o for _, o in entries])
        pre = prefix.rstrip("/") + "/"
        return {p[len(pre):]: blobs[o].decode("utf-8", "replace") for p, o in entries if o in blobs}

    def read_text(self, commit: str, path: str) -> Optional[str]:
        out = self.git("ls-tree", commit, "--", path, check=False).strip()
        if not out:
            return None
        oid = out.split()[2]
        blob = self.read_blobs([oid]).get(oid)
        return None if blob is None else blob.decode("utf-8", "replace")

    def changed_paths(self, a: str, b: str) -> List[str]:
        out = self.git("diff-tree", "-r", "--name-only", "--no-renames", a, b)
        return [line for line in out.splitlines() if line.strip()]


# ------------------------------------------------------------------------
# A local checkout or snapshot directory used as a build source.
# ------------------------------------------------------------------------
class DirSource:
    """A folder holding a mirror checkout (has Interface/...) or just the docs folder."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise MirrorError(f"not a directory: {root}")

    def describe(self) -> Build:
        v, b = None, None
        vt = self.root / "version.txt"
        if vt.is_file():
            v, b = parse_version_txt(vt.read_text(encoding="utf-8", errors="replace"))
        return Build(None, f"dir:{self.root}", "", v, b, str(self.root))

    def _resolve(self, prefix: str) -> Optional[Path]:
        p = self.root / Path(prefix)
        if p.is_dir():
            return p
        # allow pointing straight at the docs folder
        if self.root.name == Path(prefix).name:
            return self.root
        return None

    def read_dir(self, prefix: str, suffixes: Sequence[str] = (".lua",)) -> Dict[str, str]:
        base = self._resolve(prefix)
        if base is None:
            return {}
        out: Dict[str, str] = {}
        for p in sorted(base.rglob("*")):
            if p.is_file() and (not suffixes or p.name.lower().endswith(tuple(suffixes))):
                out[p.relative_to(base).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
        return out

    def list_paths(self, prefix: str) -> List[str]:
        base = self._resolve(prefix)
        if base is None:
            return []
        return [p.relative_to(base).as_posix() for p in sorted(base.rglob("*")) if p.is_file()]
