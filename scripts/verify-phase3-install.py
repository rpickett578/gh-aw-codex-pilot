"""Scoped installer-only CI for the Phase 3 candidate PR.

Never used to admit worker PRs; those must remain source-only.
"""
import os
import subprocess
import sys

BASE = "cdf9d8bb948d36f515e3cb8707e44baab07cd53a"
EXPECTED = {
    ".github/workflows/ci.yml",
    ".github/workflows/phase3-preflight.yml",
    ".github/workflows/phase3-coder-1.md",
    ".github/workflows/phase3-coder-2.md",
    ".github/workflows/phase3-coder-3.md",
    "docs/phase3-status.md",
    "scripts/phase3_gate.py",
    "scripts/phase3_snapshot.py",
    "scripts/phase3_worker_ci.py",
    "scripts/phase3_workspace_guard.py",
    "scripts/verify-phase3-install.py",
    "test/test_phase3_gate.py",
    "src/ascii-vowel-count.mjs",
    "src/strip-ascii-controls.mjs",
    "src/collapse-ascii-spaces.mjs",
    "test/ascii-vowel-count.test.mjs",
    "test/strip-ascii-controls.test.mjs",
    "test/collapse-ascii-spaces.test.mjs",
}


def require(ok, reason):
    if not ok:
        raise SystemExit("FAIL: " + reason)


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


require(os.environ["REPOSITORY"] == "rpickett578/gh-aw-codex-pilot",
        "wrong repository")
require(os.environ["HEAD_REPOSITORY"] == os.environ["REPOSITORY"],
        "fork not admitted")
require(os.environ["BASE_SHA"] == BASE and
        os.environ["HEAD_BRANCH"] == "codex/phase3-three-task-pilot",
        "not the reviewed Phase 3 installation PR")
require(git("rev-parse", "HEAD") == os.environ["HEAD_SHA"],
        "checked out wrong PR head")
changed = set(git("diff", "--name-only", BASE + "..." + os.environ["HEAD_SHA"]).splitlines())
require(changed == EXPECTED,
        "exact Phase 3 installation file inventory differs: " + repr(sorted(changed ^ EXPECTED)))
subprocess.run(["git", "diff", "--check", BASE + "..." + os.environ["HEAD_SHA"]], check=True)
for protected in [".github/workflows/phase2-chain.yml",
                  ".github/workflows/phase2-next.lock.yml",
                  ".github/workflows/phase2-repair.lock.yml",
                  ".github/workflows/phase2-review.lock.yml",
                  "scripts/phase2.py", "scripts/workspace_guard.py",
                  "scripts/verify-pilot-ci.py"]:
    require(git("rev-parse", BASE + ":" + protected) ==
            git("rev-parse", os.environ["HEAD_SHA"] + ":" + protected),
            "Phase 2 protected content changed: " + protected)
subprocess.run([sys.executable, "-m", "unittest", "discover",
                "-s", "test", "-p", "test_phase3_gate.py", "-v"], check=True)
print("PHASE3_INSTALL_PASS: exact 18-file scoped installation; unchanged Phase 2 guards; regression suite.")
