"""Exact reviewed scheduling installation CI, without AI or secret access."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

BASE = "40ebfd180e4285167d62e9d0ce680b73af5a1116"
BRANCH = "codex/phase2-scheduling-v2"
REPO = "rpickett578/gh-aw-codex-pilot"
FILES = {
    ".github/workflows/ci.yml", ".github/workflows/phase2-chain.yml",
    ".github/workflows/phase2-scheduling-worker.yml", "scripts/phase2.py",
    "scripts/verify-phase2-scheduling.py", "test/phase2-recovery.test.py",
    "test/phase2-scheduling.test.py", "docs/phase2-recovery.md", "docs/phase2-scheduling.md",
}
MANIFEST = "phase2-scheduling-install.json"


def require(ok, reason):
    if not ok:
        raise SystemExit("FAIL: " + reason)


def git(*args):
    return subprocess.check_output(["git", *args])


require(os.environ["BASE_SHA"] == BASE and os.environ["HEAD_BRANCH"] == BRANCH, "recovery installation target differs")
require(os.environ["REPOSITORY"] == REPO == os.environ["HEAD_REPOSITORY"], "repository differs")
head = os.environ["HEAD_SHA"]
require(git("rev-parse", "HEAD").decode().strip() == head, "checkout is not exact PR head")
manifest = json.loads(git("show", head + ":" + MANIFEST))
require(manifest["base"] == BASE and manifest["branch"] == BRANCH and set(manifest["files"]) == FILES,
        "exact recovery allowlist differs")
changed = set(git("diff", "--name-only", "-z", BASE + "..." + head).decode().strip("\0").split("\0"))
require(changed == FILES | {MANIFEST}, "recovery installation file set differs")
for name, digest in manifest["files"].items():
    require(git("ls-tree", head, "--", name).decode().split()[0] == "100644", "non-regular installation file")
    require(hashlib.sha256(git("show", head + ":" + name)).hexdigest() == digest, "installation bytes differ: " + name)
for test in ["test/phase2-policy.test.py", "test/phase2-recovery.test.py", "test/phase2-scheduling.test.py"]:
    subprocess.run([sys.executable, test], check=True)

# Only these documented GitHub.com features exceed current actionlint 1.7.12's schema.
# See docs/phase2-registration.md for primary-source references; other errors remain fatal.
ignores = [r'^unexpected key "queue" for "concurrency" section\.',
           r'^property "workflow_(repository|sha|ref|file_path)" is not defined in object type ']
with tempfile.TemporaryDirectory(prefix="recovery-actionlint-") as temporary:
    local = os.environ.get("ACTIONLINT")
    if local:
        executable = Path(local)
    else:
        require(sys.platform == "linux", "set ACTIONLINT to verified local v1.7.12")
        archive = Path(temporary) / "actionlint.tar.gz"
        with urllib.request.urlopen("https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz", timeout=30) as response:
            archive.write_bytes(response.read())
        require(hashlib.sha256(archive.read_bytes()).hexdigest() == "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8", "validator checksum mismatch")
        with tarfile.open(archive) as package:
            member = package.getmember("actionlint")
            require(member.isfile(), "invalid validator archive")
            executable = Path(temporary) / "actionlint"
            executable.write_bytes(package.extractfile(member).read()); executable.chmod(0o700)
    require(subprocess.check_output([str(executable), "-version"], text=True).splitlines()[0] == "1.7.12", "validator version differs")
    args = [str(executable), "-shellcheck=", "-pyflakes="]
    for pattern in ignores:
        args += ["-ignore", pattern]
    subprocess.run(args + [".github/workflows/ci.yml", ".github/workflows/phase2-scheduling-worker.yml", ".github/workflows/phase2-chain.yml"] + [
        ".github/workflows/phase2-" + stage + ".lock.yml" for stage in ["review", "repair", "next"]], check=True)
print("PASS: exact scheduling installation, 49 policy/regression tests and Actions-aware validation; native scheduling proof is a separate real CI dependency. No AI execution.")
