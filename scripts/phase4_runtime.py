"""Phase4 host-only admission and local commit guard for generic gh-aw workers.

This file cannot publish, dispatch or approve. It uses the reviewed main
manifest + fresh GitHub evidence; no agent-supplied text can expand file scope.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

from phase4_queue import QUEUE_FILE, REPO, QueueError, decide, get, live_snapshot, require, validate

# Reserve the combined worst-case coder(25+8) + independent review(12+8)
# before first paid launch; a single per-task budget cannot fund each twice.
STAGE_BUDGET = {"READY_CODING": 53, "READY_REVIEW": 53}
CONTEXT = Path("/tmp/gh-aw/phase4-task-context.json")


def host_context():
    # This must be outside the agent-editable workspace and /tmp/gh-aw mount.
    return Path(os.environ.get("PHASE4_HOST_CONTEXT_PATH", str(CONTEXT)))


def sh(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def admit(verify_checkout=True):
    require(os.environ.get("GITHUB_REPOSITORY") == REPO and
            os.environ.get("GITHUB_REF") == "refs/heads/main" and
            os.environ.get("GITHUB_RUN_ATTEMPT") == "1",
            "unexpected root job identity")
    sha = os.environ.get("GITHUB_WORKFLOW_SHA")
    require(bool(sha) and len(sha) == 40, "workflow SHA missing")
    main = get("/branches/main")
    require(main.get("commit", {}).get("sha") == sha,
            "workflow source is no longer exact approved main")
    manifest_path = Path(os.environ.get("PHASE4_QUEUE_PATH", str(QUEUE_FILE)))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = validate(manifest)
    snapshot = live_snapshot(tasks)
    selected = decide(manifest, snapshot)
    task_id = os.environ.get("PHASE4_TASK_ID")
    expected_state = os.environ.get("PHASE4_ACTION")
    require(expected_state in STAGE_BUDGET and
            selected.get("action") == expected_state and
            selected.get("task") == task_id,
            "worker stage no longer the next ordered work")
    item = tasks[selected["index"]]
    require(selected["max_ai_credits"] >= STAGE_BUDGET[expected_state],
            "task credit budget insufficient for paid worker")
    require(str(selected["issue"]) == os.environ.get("PHASE4_ISSUE"),
            "task issue changed")
    require(len(item["allowed_files"]) == 1,
            "generic v1 worker permits exactly one source file")
    if expected_state == "READY_CODING":
        if verify_checkout:
            require(sh("rev-parse", "HEAD") == sha,
                    "coder must start from exact reviewed main commit")
    else:
        require(str(selected.get("pr")) == os.environ.get("PHASE4_PR"),
                "reviewer PR identity changed")
        if verify_checkout:
            require(sh("rev-parse", "HEAD") == os.environ.get("PHASE4_HEAD"),
                    "reviewer not on pinned current PR head")
    issue = snapshot["issues"][str(item["issue"])]
    require(isinstance(issue.get("body"), str) and len(issue["body"]) <= 12000,
            "issue body absent or oversized")
    context = {"action": expected_state, "task": task_id,
               "issue": item["issue"], "issue_body": issue["body"],
               "source": item["allowed_files"][0], "install_sha": sha,
               "run_id": os.environ.get("GITHUB_RUN_ID"),
               "pr": selected.get("pr"), "head": os.environ.get("PHASE4_HEAD", "")}
    trusted = host_context()
    trusted.parent.mkdir(parents=True, exist_ok=True)
    trusted.write_text(json.dumps(context, indent=2), encoding="utf-8")
    trusted.chmod(0o400)
    if trusted != CONTEXT:
        CONTEXT.parent.mkdir(parents=True, exist_ok=True)
        CONTEXT.write_text(json.dumps(context, indent=2), encoding="utf-8")
        CONTEXT.chmod(0o400)
    print("PHASE4_RUNTIME_ADMISSION_PASS", expected_state, task_id)
    return context


def post():
    trusted = host_context()
    require(trusted.is_file(), "original trusted host context missing")
    context = json.loads(trusted.read_text(encoding="utf-8"))
    require(context.get("task") == os.environ.get("PHASE4_TASK_ID") and
            context.get("action") == os.environ.get("PHASE4_ACTION"),
            "worker context not pinned")
    root = context["install_sha"] if context["action"] == "READY_CODING" else context["head"]
    source = context["source"]
    if context["action"] == "READY_CODING":
        current = sh("rev-parse", "HEAD")
        require(current != root, "coding worker did not commit changes")
        parent = sh("rev-parse", "HEAD^")
        require(parent == root, "coding worker must produce exactly one child commit")
        paths = sh("diff", "--name-only", root, current).splitlines()
        require(paths == [source],
                "coding worker modified files outside its one approved source")
        require(sh("status", "--porcelain") == "", "coding worker left uncommitted edits")
    else:
        require(sh("rev-parse", "HEAD") == root, "reviewer moved commit")
        require(sh("status", "--porcelain") == "", "reviewer modified the checkout")
    print("PHASE4_RUNTIME_WORKTREE_PASS", context["action"], context["task"])


def main():
    require(len(sys.argv) == 2 and sys.argv[1] in ("pre", "recheck", "post"),
            "usage: phase4_runtime.py pre|recheck|post")
    if sys.argv[1] in ("pre", "recheck"):
        admit(verify_checkout=sys.argv[1] == "pre")
    else:
        post()


if __name__ == "__main__":
    try:
        main()
    except (QueueError, KeyError, OSError, ValueError,
            subprocess.CalledProcessError) as e:
        raise SystemExit("PHASE4_RUNTIME_STOP: " + str(e))
