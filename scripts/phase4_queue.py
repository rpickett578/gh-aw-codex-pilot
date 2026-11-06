"""Deterministic persistent queue selector. No write/dispatch/paid capability."""
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

REPO = "rpickett578/gh-aw-codex-pilot"
QUEUE_FILE = Path(__file__).resolve().parents[1] / "phase4" / "queue.json"
TASK_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SHA_RE = re.compile(r"[a-f0-9]{40}\Z")
SOURCE_RE = re.compile(r"src/[a-zA-Z0-9_./-]+\Z")


class QueueError(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise QueueError(reason)


def validate(manifest):
    require(isinstance(manifest, dict) and manifest.get("version") == 1 and
            manifest.get("repository") == REPO, "wrong queue version or repository")
    tasks = manifest.get("tasks")
    require(isinstance(tasks, list) and len(tasks) <= 50, "queue exceeds 50 tasks")
    ids, issues, paths = set(), set(), set()
    for item in tasks:
        require(isinstance(item, dict), "queue item must be an object")
        ident, issue = item.get("id"), item.get("issue")
        files, budget = item.get("allowed_files"), item.get("max_ai_credits")
        require(isinstance(ident, str) and TASK_RE.fullmatch(ident) and len(ident) <= 64,
                "invalid task id")
        require(type(issue) is int and 0 < issue < 1000000, "invalid task issue")
        require(isinstance(files, list) and 1 <= len(files) <= 15,
                "allowed_files must be nonempty and bounded")
        require(type(budget) is int and 0 <= budget <= 300, "invalid task budget")
        require(ident not in ids and issue not in issues, "duplicate task ID or issue")
        ids.add(ident)
        issues.add(issue)
        for f in files:
            require(isinstance(f, str) and len(f) <= 180 and SOURCE_RE.fullmatch(f) and
                    ".." not in f.split("/") and "//" not in f and
                    not any(seg.startswith(".") for seg in f.split("/")),
                    "unsafe or ambiguous allowed source path")
            require(f not in paths, "overlapping task file scope")
            paths.add(f)
        receipt = item.get("receipt")
        if receipt is None:
            require(budget > 0, "pending task requires an explicit budget")
        else:
            require(isinstance(receipt, dict) and type(receipt.get("pr")) is int and
                    receipt["pr"] > 0 and isinstance(receipt.get("head"), str) and
                    SHA_RE.fullmatch(receipt["head"]) is not None,
                    "invalid historical completion receipt")
            require(budget == 0, "completed task cannot consume further credits")
    return tasks


def branch_for(item):
    prefix = "codex/phase3-" if item.get("receipt") is not None else "codex/phase4-"
    return prefix + item["id"]


def native_review_origin(review, item, snapshot):
    actor = review.get("user") or {}
    require(actor.get("login") == "github-actions[bot]" and
            actor.get("id") == 41898282 and review.get("state") == "COMMENTED",
            "review was not published by GitHub Actions")
    body = review.get("body") or ""
    workflow = "phase3-review" if item.get("receipt") is not None else "phase4-review"
    call = '[gh-aw-workflow-call-id]: # "rpickett578%2Fgh-aw-codex-pilot%2F' + workflow + '"'
    require(call in body, "native review call identity missing")
    expr = (r'id: ([0-9]+), workflow_id: ' + re.escape(workflow) +
            r', run: https://github\.com/' + re.escape(REPO) + r'/actions/runs/\1')
    roots = re.findall(expr, body)
    require(len(roots) == 1, "native review root run missing or ambiguous")
    run = snapshot.get("runs", {}).get(roots[0])
    require(isinstance(run, dict) and
            run.get("repository", {}).get("full_name") == REPO and
            run.get("event") == "workflow_dispatch" and
            run.get("run_attempt") == 1 and
            run.get("status") == "completed" and
            run.get("conclusion") == "success" and
            run.get("path") == (".github/workflows/phase3-chain.yml" if
                                item.get("receipt") is not None else
                                ".github/workflows/phase4-chain.yml") and
            (run.get("actor") or {}).get("login") == "rpickett578" and
            (run.get("actor") or {}).get("id") == 313606620,
            "independent review root run did not pass attestation")
    return roots[0]


def review_verdict(reviews, item, head, snapshot):
    matches = []
    expr = r"\x60{3}(?:phase3|phase4)-review\s*\n(\{[^\n]+\})\n\x60{3}"
    for review in reviews:
        if review.get("state") != "COMMENTED" or review.get("commit_id") != head:
            continue
        marker = re.findall(expr, review.get("body") or "")
        if not marker:
            continue
        require(len(marker) == 1, "multiple structured review blocks")
        native_review_origin(review, item, snapshot)
        try:
            result = json.loads(marker[0])
        except (ValueError, TypeError) as exc:
            raise QueueError("malformed structured review JSON") from exc
        require(isinstance(result, dict) and result.get("task") == item["id"] and
                result.get("head") == head and result.get("verdict") in ("clean", "findings") and
                isinstance(result.get("findings"), list) and
                (result["verdict"] == "clean") == (len(result["findings"]) == 0),
                "review task/head/verdict does not match the queued work")
        matches.append(result["verdict"])
    require(len(matches) <= 1, "duplicate independent structured review")
    return matches[0] if matches else None


def task_status(item, snapshot):
    issue = snapshot.get("issues", {}).get(str(item["issue"]))
    require(isinstance(issue, dict) and issue.get("number") == item["issue"] and
            issue.get("state") == "open" and not issue.get("pull_request"),
            "task issue missing, closed or converted to a PR")
    matches = [p for p in snapshot["pulls"] if
               (p.get("head") or {}).get("ref") == branch_for(item)]
    require(len(matches) <= 1, "duplicate task PR branch")
    receipt = item.get("receipt")
    if not matches:
        require(receipt is None, "historical completed PR disappeared")
        return "READY_CODING", None
    pr = matches[0]
    head = (pr.get("head") or {}).get("sha")
    require(isinstance(head, str) and SHA_RE.fullmatch(head) and
            pr.get("state") == "open" and pr.get("draft") is True and
            not pr.get("merged_at") and (pr.get("base") or {}).get("ref") == "main",
            "task PR identity/state mismatch")
    require((pr.get("head") or {}).get("repo", {}).get("full_name") == REPO and
            (pr.get("base") or {}).get("repo", {}).get("full_name") == REPO and
            (pr.get("user") or {}).get("login") == "rpickett578" and
            (pr.get("user") or {}).get("id") == 313606620,
            "task PR must be founder-published from the approved repository")
    if receipt:
        require(pr.get("number") == receipt["pr"] and head == receipt["head"],
                "historical completion receipt changed")
    details = snapshot.get("evidence", {}).get(str(pr["number"]), {})
    files = details.get("files")
    require(isinstance(files, list) and 1 <= len(files) <= len(item["allowed_files"]) and
            len({f.get("filename") for f in files}) == len(files) and
            all(f.get("filename") in item["allowed_files"] and
                f.get("status") in ("modified", "added") for f in files),
            "PR changed files outside the exact approved task scope")
    checks = [c for c in details.get("checks", []) if c.get("name") == "synthetic-tests"]
    if not checks or any(c.get("status") != "completed" for c in checks):
        require(receipt is None, "historical completion lost CI")
        return "WAIT_CI", pr["number"]
    require(len(checks) == 1 and checks[0].get("conclusion") == "success" and
            checks[0].get("head_sha") == head and
            (checks[0].get("app") or {}).get("slug") == "github-actions",
            "CI failed, ambiguous or not published by GitHub Actions")
    ci_runs = details.get("ci_runs")
    require(isinstance(ci_runs, list) and any(
            run.get("head_sha") == head and
            run.get("path") == ".github/workflows/ci.yml" and
            run.get("event") == "pull_request" and
            run.get("run_attempt") == 1 and
            run.get("status") == "completed" and
            run.get("conclusion") == "success"
            for run in ci_runs), "required first-attempt exact-head CI workflow absent")
    verdict = review_verdict(details.get("reviews", []), item, head, snapshot)
    if verdict == "clean":
        return "DONE", pr["number"]
    require(receipt is None, "historical completion lost clean review")
    return ("READY_REPAIR" if verdict == "findings" else "READY_REVIEW"), pr["number"]


def decide(manifest, snapshot):
    tasks = validate(manifest)
    require(isinstance(snapshot, dict) and isinstance(snapshot.get("pulls"), list) and
            len(snapshot["pulls"]) < 100, "PR snapshot missing or truncated")
    done = 0
    for index, item in enumerate(tasks):
        state, pr = task_status(item, snapshot)
        if state == "DONE":
            done += 1
            continue
        return {"action": state, "task": item["id"], "issue": item["issue"],
                "index": index, "completed": done, "total": len(tasks),
                "allowed_files": item["allowed_files"],
                "max_ai_credits": item["max_ai_credits"], "pr": pr}
    return {"action": "QUEUE_EMPTY", "completed": done, "total": len(tasks)}


def get(path):
    require(path.startswith("/") and ".." not in path, "invalid GitHub API path")
    token = os.environ.get("GH_TOKEN")
    require(bool(token), "read-only GitHub token missing")
    url = "https://api.github.com/repos/" + REPO + path
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json",
               "User-Agent": "phase4-read-only-queue"}
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                        timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            if e.code in (502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise QueueError("GitHub API HTTP " + str(e.code)) from None
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise QueueError("GitHub API unavailable") from None
    raise QueueError("GitHub API unavailable")


def live_snapshot(tasks):
    pulls = get("/pulls?state=all&per_page=100")
    require(isinstance(pulls, list) and len(pulls) < 100,
            "GitHub PR inventory incomplete")
    issues, evidence, root_runs = {}, {}, {}
    for task in tasks:
        issue = task["issue"]
        issues[str(issue)] = get("/issues/" + str(issue))
        matches = [p for p in pulls if (p.get("head") or {}).get("ref") == branch_for(task)]
        if len(matches) == 1:
            pr = matches[0]
            head = (pr.get("head") or {}).get("sha")
            require(isinstance(head, str) and SHA_RE.fullmatch(head),
                    "invalid published PR SHA")
            checks = get("/commits/" + head + "/check-runs?per_page=100")
            reviews = get("/pulls/" + str(pr["number"]) + "/reviews?per_page=100")
            files = get("/pulls/" + str(pr["number"]) + "/files?per_page=100")
            ci = get("/actions/workflows/ci.yml/runs?event=pull_request&head_sha=" +
                     head + "&per_page=100")
            require(isinstance(checks, dict) and isinstance(checks.get("check_runs"), list) and
                    len(checks["check_runs"]) < 100 and isinstance(reviews, list) and
                    len(reviews) < 100 and isinstance(files, list) and len(files) < 100 and
                    isinstance(ci, dict) and isinstance(ci.get("workflow_runs"), list) and
                    len(ci["workflow_runs"]) < 100, "GitHub evidence pagination incomplete")
            for review in reviews:
                body = review.get("body") or ""
                for match in re.finditer(r'id: ([0-9]+), workflow_id: phase[34]-review,', body):
                    run_id = match.group(1)
                    if run_id not in root_runs:
                        root_runs[run_id] = get("/actions/runs/" + run_id)
            evidence[str(pr["number"])] = {
                "checks": checks["check_runs"], "reviews": reviews,
                "ci_runs": ci["workflow_runs"], "files": files}
    return {"issues": issues, "pulls": pulls, "evidence": evidence, "runs": root_runs}


def main():
    manifest = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    tasks = validate(manifest)
    if len(sys.argv) == 2 and sys.argv[1] == "--live":
        require(os.environ.get("GITHUB_REPOSITORY") == REPO and
                os.environ.get("GITHUB_REF") == "refs/heads/main",
                "live selection requires pilot main")
        snapshot = live_snapshot(tasks)
    elif len(sys.argv) == 2 and sys.argv[1] == "--stdin":
        snapshot = json.load(sys.stdin)
    else:
        raise QueueError("use --live or --stdin")
    result = decide(manifest, snapshot)
    print(json.dumps(result, sort_keys=True))
    dest = os.environ.get("GITHUB_OUTPUT")
    if dest:
        with open(dest, "a", encoding="utf-8") as f:
            f.write("action=" + result["action"] + "\n")
            f.write("task=" + str(result.get("task") or "") + "\n")


if __name__ == "__main__":
    try:
        main()
    except (QueueError, ValueError, TypeError, KeyError, OSError) as error:
        raise SystemExit("PHASE4_QUEUE_STOP: " + str(error))
