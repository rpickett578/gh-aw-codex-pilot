"""Exact, non-executing registration repair CI; never certifies AI execution."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

BASE = "fe6bf5b4a385da3957b0f5b1678b163510da47cf"
BRANCH = "codex/phase2-registration-repair"
REPO = "rpickett578/gh-aw-codex-pilot"
FILES = {
    ".github/workflows/ci.yml", ".github/workflows/phase2-review.md",
    ".github/workflows/phase2-review.lock.yml", ".github/workflows/phase2-repair.md",
    ".github/workflows/phase2-repair.lock.yml", "scripts/verify-phase2-registration.py",
    "docs/phase2-registration.md",
}
MANIFEST = "phase2-registration.json"
WORKFLOWS = [".github/workflows/phase2-chain.yml"] + [
    ".github/workflows/phase2-" + stage + ".lock.yml" for stage in ["review", "repair", "next"]]


def require(ok, reason):
    if not ok:
        raise SystemExit("FAIL: " + reason)


def git(*args):
    return subprocess.check_output(["git", *args])


require(os.environ["BASE_SHA"] == BASE, "repair base differs")
require(os.environ["HEAD_BRANCH"] == BRANCH, "repair branch differs")
require(os.environ["REPOSITORY"] == REPO == os.environ["HEAD_REPOSITORY"], "repository differs")
head = os.environ["HEAD_SHA"]
require(git("rev-parse", "HEAD").decode().strip() == head, "checkout is not exact PR head")
manifest = json.loads(git("show", head + ":" + MANIFEST))
require(manifest["base"] == BASE and manifest["branch"] == BRANCH, "manifest target differs")
require(set(manifest["files"]) == FILES, "exact repair allowlist differs")
changed = set(git("diff", "--name-only", "-z", BASE + "..." + head).decode().strip("\0").split("\0"))
require(changed == FILES | {MANIFEST}, "repair file set differs")
for name, digest in manifest["files"].items():
    require(git("ls-tree", head, "--", name).decode().split()[0] == "100644", "non-regular repair file")
    require(hashlib.sha256(git("show", head + ":" + name)).hexdigest() == digest, "repair bytes differ: " + name)
for stage, removed in [("review", ["  EXPECTED_HEAD: ${{ inputs.head_sha }}\n", "  REVIEW_ID: ${{ inputs.review_id }}\n"]),
                       ("repair", ["  EXPECTED_HEAD: ${{ inputs.head_sha }}\n"])]:
    name = ".github/workflows/phase2-" + stage + ".md"
    original = git("show", BASE + ":" + name).decode()
    for line in removed:
        require(original.count(line) == 1, "original input reference differs")
        original = original.replace(line, "")
    require(git("show", head + ":" + name).decode() == original, "source changed beyond unused input removal")

subprocess.run([sys.executable, "test/phase2-policy.test.py"], check=True)
# actionlint 1.7.12 predates two documented GitHub.com additions. Suppress only
# these specific diagnostic classes, never input, linkage, permissions or DAG errors.
# https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency
# https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#job-context
ignores = [r'^unexpected key "queue" for "concurrency" section\.',
           r'^property "workflow_(repository|sha|ref|file_path)" is not defined in object type ']
with tempfile.TemporaryDirectory(prefix="actionlint-") as temporary:
    local = os.environ.get("ACTIONLINT")
    if local:
        executable = Path(local)
    else:
        require(sys.platform == "linux", "set ACTIONLINT to checksum-verified local v1.7.12 on non-Linux")
        archive = Path(temporary) / "actionlint.tar.gz"
        urllib.request.urlretrieve("https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz", archive)
        require(hashlib.sha256(archive.read_bytes()).hexdigest() == "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8", "actionlint release checksum mismatch")
        with tarfile.open(archive) as package:
            member = package.getmember("actionlint")
            require(member.isfile(), "actionlint is not a regular archive file")
            executable = Path(temporary) / "actionlint"
            executable.write_bytes(package.extractfile(member).read())
            executable.chmod(0o700)
    version = subprocess.check_output([str(executable), "-version"], text=True)
    require(version.splitlines()[0] == "1.7.12", "actionlint version differs")
    args = [str(executable), "-shellcheck=", "-pyflakes="]
    for pattern in ignores:
        args += ["-ignore", pattern]
    subprocess.run(args + WORKFLOWS, check=True)
print("PASS: exact registration repair, 17 policy tests and four Actions-aware workflow validations; no AI execution.")
