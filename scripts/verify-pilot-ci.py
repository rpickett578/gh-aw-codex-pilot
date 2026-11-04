"""Fail-closed CI for one exact bootstrap, then source-only functional PRs."""
import hashlib
import os
import re
import subprocess
from pathlib import Path

INITIAL = "f6f81ff4037625affa0f4d9caab7622b06a24206"
README_BLOB = "4667202c0751ffe4d5b60eceec8153665914e955"
SELF_SHA256 = "4c860ba07f302cb8d83001a6bcdf79306dec2d1db58e120bdc109d20103b2e83"
EXPECTED = {
    "AGENTS.md": "63bc6cbae5a03eaac559cd80eef4b04d8469f5b7e15e5d7078ca194a028e69c7",
    "TASK.md": "46dcb03d9c2cf3a1b76be9348c771743afabdf25d7cbf6bee745a08e3eb775e0",
    "src/slugify.mjs": "51a171866ca8c128fe15fa7514d35becff57f98b1ff08432d4fe36b0e36fed7b",
    "test/slugify.test.mjs": "6b02e4e6cfb7be68446bc86952bceefa11dc73b63973627e018fb4c184e2c509",
    ".github/workflows/ci.yml": "f11cba642af004932b7da7fba93910fc918be4cef88eba2d4a0fcbfb3929c55e",
    ".github/workflows/synthetic-fix.lock.yml": "45b0ca9dde5d2977ec587dc105be0927823ba3e6cda63c77ca5e83699f260152",
}
VERIFIER = "scripts/verify-pilot-ci.py"


def require(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)


def git(*args):
    return subprocess.check_output(["git", *args])


def blob(revision, name):
    return git("show", revision + ":" + name)


def tree(revision):
    result = {}
    for entry in git("ls-tree", "-rz", revision).split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        result[name.decode("utf-8")] = (mode, kind, oid)
    return result


def run_tests(expected_pass, expected_fail):
    outcome = subprocess.run(
        ["node", "--test", "--test-reporter=tap", "test/slugify.test.mjs"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="strict", timeout=30,
    )
    print(outcome.stdout, end="")
    require(outcome.returncode == (1 if expected_fail else 0), "unexpected test exit")
    for field, count in {"tests": 19, "pass": expected_pass,
                         "fail": expected_fail, "skipped": 0,
                         "cancelled": 0, "todo": 0}.items():
        require(re.search(r"^# " + field + " " + str(count) + r"$",
                          outcome.stdout, re.M) is not None,
                "unexpected test count: " + field)


base = os.environ["BASE_SHA"]
head = os.environ["HEAD_SHA"]
for revision in [base, head]:
    require(re.fullmatch(r"[a-f0-9]{40}", revision), "invalid commit SHA")
require(git("rev-parse", "HEAD").decode().strip() == head, "checkout is not PR head")
base_tree = tree(base)
head_tree = tree(head)

if base == INITIAL:
    require(os.environ["REPOSITORY"] == "rpickett578/gh-aw-codex-pilot",
            "wrong bootstrap repository")
    require(os.environ["HEAD_REPOSITORY"] == os.environ["REPOSITORY"],
            "bootstrap must be same-repository")
    require(os.environ["HEAD_BRANCH"] == "codex/bootstrap-inert-pilot",
            "wrong bootstrap branch")
    require(base_tree == {"README.md": ("100644", "blob", README_BLOB)},
            "initial tree differs")
    require(set(head_tree) == {"README.md", VERIFIER, *EXPECTED},
            "bootstrap file set differs")
    require(head_tree["README.md"] == base_tree["README.md"], "README changed")
    for name, digest in EXPECTED.items():
        require(head_tree[name][:2] == ("100644", "blob"), "non-regular file: " + name)
        require(hashlib.sha256(blob(head, name)).hexdigest() == digest,
                "bootstrap bytes differ: " + name)
    require(head_tree[VERIFIER][:2] == ("100644", "blob"), "non-regular verifier")
    source = blob(head, VERIFIER)
    canonical, count = re.subn(
        rb'^SELF_SHA256 = "[a-f0-9]{64}"$', b'SELF_SHA256 = "SELF"',
        source, flags=re.M,
    )
    require(count == 1 and hashlib.sha256(canonical).hexdigest() == SELF_SHA256,
            "bootstrap verifier bytes differ")
    run_tests(10, 9)
    print("PASS: exact inert bootstrap; 19-test baseline has expected 9 failures.")
else:
    changed = git("diff", "--name-only", "-z", base + "..." + head).split(b"\0")
    require(changed == [b"src/slugify.mjs", b""], "normal PR must change source only")
    require(head_tree["src/slugify.mjs"][:2] == ("100644", "blob"), "non-regular source")
    require(len(blob(head, "src/slugify.mjs")) <= 16 * 1024, "source exceeds 16 KB")
    require(git("diff", "--numstat", base + "..." + head).strip(), "empty source change")
    run_tests(19, 0)
    print("PASS: source-only PR; all 19 functional tests passed on exact head.")
