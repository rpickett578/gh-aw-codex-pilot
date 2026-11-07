"""Pilot Phase4 dispatcher: deterministic bounded reservations, no worker launch.

This module has no workflow-dispatch endpoint. A reservation is an irreversible
claim on a task/stage budget, not permission to pay for a second attempt.
The workflow initially invokes only the read-only --preview mode.
"""
import base64
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

from phase4_queue import (REPO, QUEUE_FILE, QueueError, decide, get,
                          live_snapshot, require, validate)

LEDGER_BRANCH = "phase4-dispatch-ledger"
LEDGER_PATH = "phase4/dispatch-ledger.json"
STAGE_CREDITS = {"READY_CODING": 33, "READY_REVIEW": 20}
TASK_ENVELOPE = sum(STAGE_CREDITS.values())
MAX_CLAIMS = 100
SHA_SIZE = 40


def initial_ledger():
    return {"version": 1, "repository": REPO, "claims": []}


def validate_ledger(ledger):
    require(isinstance(ledger, dict) and set(ledger) ==
            {"version", "repository", "claims"} and ledger["version"] == 1 and
            ledger["repository"] == REPO and
            isinstance(ledger["claims"], list) and
            len(ledger["claims"]) <= MAX_CLAIMS, "invalid dispatch ledger")
    seen = set()
    for claim in ledger["claims"]:
        require(isinstance(claim, dict) and set(claim) ==
                {"task", "stage", "issue", "source", "pr", "head", "cost",
                 "run_id", "install_sha"} and
                isinstance(claim["task"], str) and 1 <= len(claim["task"]) <= 64 and
                claim["stage"] in STAGE_CREDITS and
                type(claim["issue"]) is int and claim["issue"] > 0 and
                isinstance(claim["source"], str) and
                claim["source"].startswith("src/") and
                claim["cost"] == STAGE_CREDITS[claim["stage"]] and
                type(claim["run_id"]) is int and claim["run_id"] > 0 and
                isinstance(claim["install_sha"], str) and
                len(claim["install_sha"]) == SHA_SIZE and
                all(ch in "0123456789abcdef" for ch in claim["install_sha"]) and
                (claim["pr"] is None or type(claim["pr"]) is int and claim["pr"] > 0) and
                isinstance(claim["head"], str) and
                (not claim["head"] or
                 len(claim["head"]) == SHA_SIZE and
                 all(ch in "0123456789abcdef" for ch in claim["head"])),
                "invalid ledger reservation")
        key = (claim["task"], claim["stage"])
        require(key not in seen, "duplicate stage reservation in ledger")
        seen.add(key)
    return ledger


def decide_claim(manifest, snapshot, ledger, run_id, install_sha):
    """Pure planning. Existing reservations are never retried automatically."""
    validate_ledger(ledger)
    tasks = validate(manifest)
    selected = decide(manifest, snapshot)
    action = selected["action"]
    if action not in STAGE_CREDITS:
        return {"decision": "NO_LAUNCH", "reason": action}
    require(type(run_id) is int and run_id > 0 and isinstance(install_sha, str) and
            len(install_sha) == SHA_SIZE and
            all(ch in "0123456789abcdef" for ch in install_sha),
            "invalid run identity")
    item = tasks[selected["index"]]
    task = item["id"]
    require(len(item["allowed_files"]) == 1, "only one source per pilot task")
    require(item["max_ai_credits"] >= TASK_ENVELOPE,
            "task budget cannot cover coder plus reviewer")
    existing = [c for c in ledger["claims"] if c["task"] == task]
    require(all(c["issue"] == item["issue"] and
                c["source"] == item["allowed_files"][0] for c in existing),
            "ledger reservation conflicts with approved task")
    if any(c["stage"] == action for c in existing):
        prior = next(c for c in existing if c["stage"] == action)
        return {"decision": "HELD",
                "reason": ("stale-main claim; reconcile only after proving no paid"
                           " worker launched" if prior["install_sha"] != install_sha
                           else "already reserved"),
                "task": task, "stage": action}
    if action == "READY_REVIEW":
        require(any(c["stage"] == "READY_CODING" for c in existing),
                "review lacks prior coder reservation")
    cost = STAGE_CREDITS[action]
    require(sum(c["cost"] for c in existing) + cost <= item["max_ai_credits"],
            "cumulative reserved credits exceed approved task budget")
    pr = selected.get("pr")
    head = ""
    if action == "READY_REVIEW":
        matches = [p for p in snapshot["pulls"] if p.get("number") == pr]
        require(len(matches) == 1 and
                isinstance((matches[0].get("head") or {}).get("sha"), str) and
                len(matches[0]["head"]["sha"]) == SHA_SIZE,
                "review PR head missing")
        head = matches[0]["head"]["sha"]
    else:
        require(pr is None, "coder stage already has task PR")
    claim = {"task": task, "stage": action, "issue": item["issue"],
             "source": item["allowed_files"][0], "pr": pr, "head": head,
             "cost": cost, "run_id": run_id, "install_sha": install_sha}
    return {"decision": "RESERVE", "claim": claim,
            "remaining_credits": item["max_ai_credits"] -
                                 sum(c["cost"] for c in existing) - cost}


def read_ledger():
    """The ledger is a separate reviewed-purpose branch; never invent it."""
    response = get("/contents/" + LEDGER_PATH + "?ref=" + LEDGER_BRANCH)
    require(isinstance(response, dict) and
            response.get("encoding") == "base64" and
            isinstance(response.get("sha"), str) and
            isinstance(response.get("content"), str),
            "durable ledger absent or malformed")
    try:
        content = base64.b64decode(response["content"], validate=False)
        ledger = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise QueueError("cannot decode ledger") from exc
    return validate_ledger(ledger), response["sha"]


def write_claim(ledger, blob_sha):
    """One optimistic-conditional write; conflicts stop, never retry or launch."""
    require(isinstance(blob_sha, str) and len(blob_sha) == SHA_SIZE,
            "missing ledger blob SHA")
    token = os.environ.get("GH_TOKEN")
    require(bool(token), "GitHub write token missing")
    data = {"message": "Reserve approved Phase4 worker stage (pilot ledger)",
            "branch": LEDGER_BRANCH, "sha": blob_sha,
            "content": base64.b64encode((json.dumps(ledger, sort_keys=True,
                    indent=2) + "\n").encode()).decode()}
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + "/contents/" + LEDGER_PATH,
        data=json.dumps(data).encode(), method="PUT",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "phase4-pilot-dispatch-ledger"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise QueueError("ledger reservation failed; no worker authorized") from exc
    require(isinstance(result, dict) and
            isinstance(result.get("commit"), dict) and
            isinstance(result.get("content"), dict),
            "ledger commit not confirmed")
    return result["commit"].get("sha")


def require_current_main(approved_sha):
    """Revalidate authority immediately around an effective ledger reservation."""
    require(get("/branches/main").get("commit", {}).get("sha") == approved_sha,
            "approved main changed; do not reserve or launch a worker")


def require_root_identity():
    require(os.environ.get("GITHUB_REPOSITORY") == REPO and
            os.environ.get("GITHUB_REF") == "refs/heads/main" and
            os.environ.get("GITHUB_RUN_ATTEMPT") == "1" and
            os.environ.get("GITHUB_WORKFLOW") ==
            "Phase 4 dispatch planning (no paid workers)",
            "not the approved pilot main workflow")
    sha = os.environ.get("GITHUB_WORKFLOW_SHA")
    require(isinstance(sha, str) and len(sha) == SHA_SIZE and
            get("/branches/main").get("commit", {}).get("sha") == sha,
            "workflow SHA no longer reviewed main")
    return sha


def main():
    require(len(sys.argv) == 2 and
            sys.argv[1] in ("--preview", "--claim"), "use --preview or --claim")
    sha = require_root_identity()
    manifest = json.loads(Path(QUEUE_FILE).read_text(encoding="utf-8"))
    tasks = validate(manifest)
    snapshot = live_snapshot(tasks)
    if sys.argv[1] == "--preview":
        print(json.dumps({"mode": "READ_ONLY", "selected": decide(manifest, snapshot)},
                         sort_keys=True))
        return
    # An effective call to --claim is NOT installed or scheduled in this PR.
    require(os.environ.get("PHASE4_CLAIMS_ENABLED") == "reviewed-install",
            "claim writes are disabled")
    ledger, blob_sha = read_ledger()
    result = decide_claim(manifest, snapshot, ledger,
                          int(os.environ["GITHUB_RUN_ID"]), sha)
    if result["decision"] != "RESERVE":
        print(json.dumps(result, sort_keys=True))
        return
    require_current_main(sha)
    ledger["claims"].append(result["claim"])
    commit = write_claim(ledger, blob_sha)
    require_current_main(sha)
    require(isinstance(commit, str) and len(commit) == SHA_SIZE,
            "no durable ledger receipt")
    print(json.dumps({"decision": "RESERVED_NO_WORKER_LAUNCH",
                      "claim": result["claim"], "ledger_commit": commit},
                     sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (QueueError, KeyError, ValueError, OSError) as exc:
        raise SystemExit("PHASE4_DISPATCH_STOP: " + str(exc))
