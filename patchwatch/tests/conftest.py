from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

DOC = "Interface/AddOns/Blizzard_APIDocumentationGenerated"
DEP = "Interface/AddOns/Blizzard_Deprecated"
CON = "Interface/AddOns/Blizzard_ProjectConstants"


def make_tree(dest: Path, which: str, version: str) -> Path:
    """Lay out a mirror-like checkout ('old' or 'new' fixture set) under dest."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / "version.txt").write_text(version + "\n", encoding="utf-8")
    shutil.copytree(FIX / f"docs_{which}", dest / DOC)
    shutil.copytree(FIX / f"deprecated_{which}", dest / DEP)
    shutil.copytree(FIX / f"constants_{which}", dest / CON)
    return dest


def git(cwd: Path, *args: str) -> str:
    # inherit the environment (Windows git needs SYSTEMROOT etc.), pin identity and dates
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
               GIT_AUTHOR_DATE="2026-09-16T18:00:00Z", GIT_COMMITTER_DATE="2026-09-16T18:00:00Z")
    return subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env).stdout.decode()


def commit_tree(repo: Path, which: str, version: str, build: int, date: str) -> str:
    """Replace the work tree with a fixture set and commit it as '<version> (<build>)'."""
    for p in repo.iterdir():
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    tmp = repo.parent / f"_tree_{which}"
    make_tree(tmp, which, f"{version}.{build}")
    for p in tmp.iterdir():
        shutil.move(str(p), str(repo / p.name))
    shutil.rmtree(tmp)
    git(repo, "add", "-A")
    env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    subprocess.run(["git", "commit", "-q", "-m", f"{version} ({build})"], cwd=repo, check=True, env=env)
    return git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture
def fake_mirror(tmp_path: Path):
    """A local git repo shaped like Gethe/wow-ui-source with a 'forever' branch.

    Commits: Initial commit, 1.60.1 (100) [old docs], 1.60.1 (101) [same docs],
    1.60.1 (102) [new docs].  Partial-clone serving is enabled so the
    blob:none + batch prefetch code path runs against it.
    """
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    repo = tmp_path / "remote repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "forever")
    git(repo, "config", "uploadpack.allowFilter", "true")
    git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")
    (repo / "README.md").write_text("mirror\n")
    git(repo, "add", "-A")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
               GIT_AUTHOR_DATE="2026-09-15T10:00:00Z", GIT_COMMITTER_DATE="2026-09-15T10:00:00Z")
    subprocess.run(["git", "commit", "-q", "-m", "Initial commit"], cwd=repo, check=True, env=env)
    c100 = commit_tree(repo, "old", "1.60.1", 100, "2026-09-16T18:28:00Z")
    (repo / "README.md").write_text("mirror\nrebuild\n")
    git(repo, "add", "-A")
    env2 = dict(env, GIT_AUTHOR_DATE="2026-09-17T01:00:00Z", GIT_COMMITTER_DATE="2026-09-17T01:00:00Z")
    subprocess.run(["git", "commit", "-q", "-m", "1.60.1 (101)"], cwd=repo, check=True, env=env2)
    c101 = git(repo, "rev-parse", "HEAD").strip()
    c102 = commit_tree(repo, "new", "1.60.1", 102, "2026-10-01T22:56:00Z")
    return {"path": repo, "url": repo.as_uri(), "commits": {100: c100, 101: c101, 102: c102}}


@pytest.fixture
def addon_dir() -> Path:
    return FIX / "addons" / "PatchwatchFixture"
