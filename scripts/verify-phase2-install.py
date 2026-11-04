"""Validate this exact human-reviewed installation; never certify an AI task."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

BASE = "d5c947f0000a32656eb50a55fca0270e28f6aafa"
REPO = "rpickett578/gh-aw-codex-pilot"
FILES = {
    ".gitattributes", ".github/workflows/ci.yml", ".github/workflows/phase2-chain.yml",
    ".github/workflows/phase2-review.md", ".github/workflows/phase2-review.lock.yml",
    ".github/workflows/phase2-repair.md", ".github/workflows/phase2-repair.lock.yml",
    ".github/workflows/phase2-next.md", ".github/workflows/phase2-next.lock.yml",
    "AGENTS.md", "docs/phase2.md", "fixtures/seeded-defect/README.md", "fixtures/seeded-defect/slugify.mjs",
    "scripts/phase2.py", "scripts/verify-phase2-install.py", "scripts/verify-pilot-ci.py",
    "src/reverse-ascii.mjs", "test/phase2-policy.test.py", "test/reverse-ascii.test.mjs",
}


def require(ok, reason):
    if not ok:
        raise SystemExit("FAIL: " + reason)


def git(*args):
    return subprocess.check_output(["git", *args])


require(os.environ["BASE_SHA"] == BASE, "installation base differs")
require(os.environ["HEAD_BRANCH"] == "codex/phase2-issue-3", "installation branch differs")
require(os.environ["REPOSITORY"] == REPO and os.environ["HEAD_REPOSITORY"] == REPO, "repository differs")
head = os.environ["HEAD_SHA"]
require(git("rev-parse", "HEAD").decode().strip() == head, "checkout is not exact PR head")
manifest = json.loads(git("show", head + ":phase2-install.json"))
require(manifest["base"] == BASE and manifest["branch"] == "codex/phase2-issue-3", "manifest target differs")
expected = set(manifest["files"]) | {"phase2-install.json"}
require(set(manifest["files"]) == FILES, "exact installation allowlist differs")
changed = set(git("diff", "--name-only", "-z", BASE + "..." + head).decode().strip("\0").split("\0"))
require(changed == expected, "installation file set differs")
for path, digest in manifest["files"].items():
    mode = git("ls-tree", head, "--", path).decode().split()[0]
    require(mode == "100644", "installation file must be regular: " + path)
    require(hashlib.sha256(git("show", head + ":" + path)).hexdigest() == digest, "installation bytes differ: " + path)
for path in ["src/slugify.mjs", "test/slugify.test.mjs", ".github/workflows/synthetic-fix.lock.yml"]:
    require(git("show", BASE + ":" + path) == git("show", head + ":" + path), "Phase 1 boundary changed")

subprocess.run(["python3" if os.name != "nt" else "python", "test/phase2-policy.test.py"], check=True)
for filename, total, passed, failed in [("test/slugify.test.mjs", 19, 10, 9), ("test/reverse-ascii.test.mjs", 8, 0, 8)]:
    result = subprocess.run(["node", "--test", "--test-reporter=tap", filename], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
    require(result.returncode == 1, "fixture must remain deliberately unimplemented")
    for field, value in [("tests", total), ("pass", passed), ("fail", failed)]:
        require(re.search(r"^# " + field + " " + str(value) + r"$", result.stdout, re.M), "fixture baseline changed")
    print("Validated deliberate fixture baseline:", filename, total, passed, failed)
print("PASS: exact Phase 2 installation and deterministic policy controls; no AI task executed.")
