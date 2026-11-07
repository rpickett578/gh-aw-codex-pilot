"""Verify native Phase4 source-only task PR against trusted reviewed-main queue.

Run this script from the *base* commit in required CI. It never modifies GitHub.
The worker may create one new source file, never tests/config/policy.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from phase4_queue import REPO, TASK_RE, QueueError, require, validate

PREFIX = "codex/phase4-"
EXPECTED_CREDITS = 53


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def approved_task(manifest, head_branch):
    require(isinstance(head_branch, str) and head_branch.startswith(PREFIX),
            "not a Phase4 task branch")
    ident = head_branch[len(PREFIX):]
    require(TASK_RE.fullmatch(ident) is not None, "invalid task branch name")
    tasks = validate(manifest)
    matches = [t for t in tasks if t["id"] == ident]
    require(len(matches) == 1, "task is not in reviewed-main queue")
    task = matches[0]
    require(task.get("receipt") is None, "completed task cannot be rerun")
    require(len(task["allowed_files"]) == 1,
            "pilot worker requires exactly one approved source")
    require(task["max_ai_credits"] >= EXPECTED_CREDITS,
            "queue did not reserve full coder/reviewer credit envelope")
    fixture = "test/" + ident + ".test.mjs"
    return task, fixture


def validate_changed_files(source_path, changed):
    require(changed == [source_path], "task PR must edit exactly its approved source")


def verify():
    repo = os.environ.get("REPOSITORY")
    head_repo = os.environ.get("HEAD_REPOSITORY")
    base = os.environ.get("BASE_SHA")
    head = os.environ.get("HEAD_SHA")
    branch = os.environ.get("HEAD_BRANCH")
    require(repo == REPO and head_repo == REPO, "foreign repository task PR")
    require(all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{40}", x)
                for x in (base, head)), "missing exact PR SHAs")
    require(git("rev-parse", "HEAD") == head, "runner is not checked out to PR head")
    manifest = json.loads(git("show", base + ":phase4/queue.json"))
    task, fixture = approved_task(manifest, branch)
    source_path = task["allowed_files"][0]

    changed = git("diff", "--name-only", base + "..." + head).splitlines()
    validate_changed_files(source_path, changed)
    modes = git("ls-tree", head, "--", source_path).splitlines()
    require(len(modes) == 1 and modes[0].startswith("100644 blob "),
            "source must be a regular committed file")
    require(len(git("show", head + ":" + source_path).encode("utf-8")) <= 16384,
            "source exceeds 16 KiB")
    # The test file must already exist on trusted main (never from the coder).
    fixture_bytes = subprocess.check_output(["git", "show", base + ":" + fixture])
    require(0 < len(fixture_bytes) <= 32768, "immutable task test missing or oversized")
    require(Path(fixture).read_bytes() == fixture_bytes,
            "worker checkout changed immutable tests")
    # The native PR is already scope-checked; no agent input can alter this path.
    process = subprocess.run(["node", "--test", "--test-reporter=tap", fixture],
                             text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=50)
    print(process.stdout, end="")
    require(process.returncode == 0 and
            re.search(r"^# fail 0$", process.stdout, re.M) is not None and
            re.search(r"^# tests ([1-9][0-9]*)$", process.stdout, re.M) is not None,
            "immutable task functional tests did not pass")
    print("PHASE4_APPROVED_SOURCE_CI_PASS", task["id"], source_path)


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 1, "no arguments allowed; CI provides fixed inputs")
        verify()
    except (QueueError, ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit("PHASE4_SOURCE_CI_STOP: " + str(error))
