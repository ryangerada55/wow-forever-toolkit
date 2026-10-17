#!/usr/bin/env python3
"""Self-test for check_paths.py: GoodAddon must be clean, BrokenAddon must give exactly the
findings in expected_BrokenAddon.txt. Runs on Linux, macOS and Windows (stdlib only).
usage: python3 tests/selftest.py"""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
lint = os.path.join(here, "..", "check_paths.py")


def run(name):
    p = subprocess.run([sys.executable, lint, os.path.join(here, "fixtures", name)],
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout.splitlines()


ok = True
rc, out = run("GoodAddon")
if rc != 0 or len(out) != 1:
    ok = False
    print("FAIL GoodAddon: expected no findings, got rc=%d:\n  %s" % (rc, "\n  ".join(out)))
rc, out = run("BrokenAddon")
with open(os.path.join(here, "expected_BrokenAddon.txt"), encoding="utf-8") as f:
    expected = f.read().splitlines()
if rc != 1 or out != expected:
    ok = False
    print("FAIL BrokenAddon: rc=%d (want 1); diff:" % rc)
    for line in sorted(set(out) ^ set(expected)):
        print("  %s %s" % ("+" if line in out else "-", line))
print("selftest: " + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
