"""Scoped installer-only CI for the Phase 3 candidate PR.

Never used to admit worker PRs; those must remain source-only.
"""
import os
import hashlib
import subprocess
import sys

BASE = "cdf9d8bb948d36f515e3cb8707e44baab07cd53a"
EXPECTED = {
    ".github/workflows/ci.yml",
    ".github/workflows/phase3-preflight.yml",
    ".github/workflows/phase3-chain.yml",
    ".github/workflows/phase3-review.md",
    ".github/workflows/phase3-repair-1.md",
    ".github/workflows/phase3-repair-2.md",
    ".github/workflows/phase3-repair-3.md",
    ".github/workflows/phase3-coder-1.md",
    ".github/workflows/phase3-coder-2.md",
    ".github/workflows/phase3-coder-3.md",
    "docs/phase3-status.md",
    "scripts/phase3_gate.py",
    "scripts/phase3_snapshot.py",
    "scripts/phase3_worker_ci.py",
    "scripts/phase3_wait.py",
    "scripts/phase3_repair_evidence.py",
    "scripts/phase3_route.py",
    "scripts/phase3_workspace_guard.py",
    "scripts/verify-phase3-install.py",
    "test/test_phase3_gate.py",
    "test/test_phase3_repair.py",
    "src/ascii-vowel-count.mjs",
    "src/strip-ascii-controls.mjs",
    "src/collapse-ascii-spaces.mjs",
    "test/ascii-vowel-count.test.mjs",
    "test/strip-ascii-controls.test.mjs",
    "test/collapse-ascii-spaces.test.mjs",
}


LOCK_SHA256 = {
    ".github/workflows/phase3-coder-1.lock.yml": "4f3877524da8038cf8a648e24a2d2f27f1a24cd061a32ef238654b8dc9c35184",
    ".github/workflows/phase3-coder-2.lock.yml": "03ad2d0c3030cd8f8e5a860a4485210a40676a922c8e3f87faff7e88baf384d5",
    ".github/workflows/phase3-coder-3.lock.yml": "7eb898f746fdde939c561fb7bfae5d77e6bd1788612ddce57f7495d85358f6a6",
    ".github/workflows/phase3-review.lock.yml": "7da13a3c0aa3bc22d77320df46cbfdb308d7a4266e16b49cae0ae764d158b355",
    ".github/workflows/phase3-repair-1.lock.yml": "c250ec3765a95a12e559f9a5b7e6220aaea3dccc19a2bc4b2d9324e01f56a1ac",
    ".github/workflows/phase3-repair-2.lock.yml": "7bdbbac51fc953a571aa965be5f0813fb096eeafa7b8170d878c61c66f1c7110",
    ".github/workflows/phase3-repair-3.lock.yml": "c44a99fce74690014487d1f2393c354bb5edc05d36920aeca8df203067442934",
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
compiled = changed & set(LOCK_SHA256)
base_locks = {p for p in LOCK_SHA256 if 'repair-' not in p}
repair_locks = set(LOCK_SHA256) - base_locks
require(compiled in (base_locks, base_locks | repair_locks),
        "partial compiled lock installation prohibited")
allowed = EXPECTED | compiled
require(changed == allowed,
        "exact Phase 3 installation file inventory differs: " + repr(sorted(changed ^ allowed)))
for lock in compiled:
    recorded = hashlib.sha256(subprocess.check_output(["git", "show", os.environ["HEAD_SHA"] + ":" + lock])).hexdigest()
    require(recorded == LOCK_SHA256[lock], "compiled lock checksum differs: " + lock)
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
for pattern in ("test_phase3_gate.py", "test_phase3_repair.py"):
    subprocess.run([sys.executable, "-m", "unittest", "discover",
                    "-s", "test", "-p", pattern, "-v"], check=True)
print("PHASE3_INSTALL_PASS: bounded installer, exact 4-or-7 compiled locks; unchanged Phase 2 guards; regression suite.")
