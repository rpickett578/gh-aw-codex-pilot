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


def required_tests(tap_text, expected):
    """Use the runner's final TAP summary, not a positive but partial count."""
    require(type(expected) is int and 1 <= expected <= 200,
            "invalid reviewed fixture test count")
    reports = {}
    for field in ("tests", "pass", "fail", "cancelled", "skipped", "todo"):
        matches = re.findall(r"^# " + field + r" (\d+)$",
                             tap_text, re.M)
        require(len(matches) > 0, "missing TAP summary: " + field)
        reports[field] = int(matches[-1])
    require(reports["tests"] == expected and reports["pass"] == expected and
            all(reports[field] == 0 for field in
                ("fail", "cancelled", "skipped", "todo")),
            "actual fixture case count or outcome differs from approved manifest")


def sandbox_command(source_path, fixture_path):
    """Execute the reviewed fixture directly under Node's enforce permission model.

    No child processes, worker threads, filesystem writes or unrelated file
    reads are granted. Direct node:test execution avoids the --test runner's
    own subprocess, while retaining its trusted TAP summary.
    """
    source = str(Path(source_path).resolve(strict=True))
    fixture = str(Path(fixture_path).resolve(strict=True))
    require(source != fixture and
            Path(source).is_file() and Path(fixture).is_file(),
            "source/fixture missing or identical")
    return ["node", "--permission", "--allow-fs-read=" + fixture,
            "--allow-fs-read=" + source, fixture]


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
    require(len(subprocess.check_output(["git", "show", head + ":" + source_path])) <= 16384,
            "source exceeds 16 KiB")
    # The test file must already exist on trusted main (never from the coder).
    fixture_bytes = subprocess.check_output(["git", "show", base + ":" + fixture])
    require(0 < len(fixture_bytes) <= 32768, "immutable task test missing or oversized")
    require(Path(fixture).read_bytes() == fixture_bytes,
            "worker checkout changed immutable tests")
    meta_path = fixture.removesuffix(".test.mjs") + ".test-meta.json"
    meta_bytes = subprocess.check_output(["git", "show", base + ":" + meta_path])
    require(0 < len(meta_bytes) <= 2048, "missing fixture metadata")
    metadata = json.loads(meta_bytes)
    require(isinstance(metadata, dict) and
            set(metadata) == {"expected_tests"}, "invalid fixture metadata")
    require(Path(meta_path).read_bytes() == meta_bytes,
            "worker checkout changed immutable fixture metadata")
    expected = metadata["expected_tests"]
    require(type(expected) is int and 1 <= expected <= 200,
            "invalid expected fixture case count")
    # The native PR is already scope-checked; no agent input can alter this path.
    process = subprocess.run(sandbox_command(source_path, fixture),
                             text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=50,
                             env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                  "CI": "true"})
    print(process.stdout, end="")
    require(process.returncode == 0, "immutable task runner exited unsuccessfully")
    required_tests(process.stdout, expected)
    print("PHASE4_APPROVED_SOURCE_CI_PASS", task["id"], source_path)


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 1, "no arguments allowed; CI provides fixed inputs")
        verify()
    except (QueueError, ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit("PHASE4_SOURCE_CI_STOP: " + str(error))
