"""Read-only GitHub snapshot for the Phase 3 queue decision function.

No POST/PATCH/DELETE methods, no workflow dispatch, and no token logging.
The caller must independently enforce the stage authorization and budget.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

from phase3_gate import TASKS, REPO, Stop, check, decide


def api(path, optional=False):
    check(path.startswith("/") and ".." not in path, "invalid API path")
    token = os.environ.get("GH_TOKEN", "")
    check(bool(token), "GH_TOKEN missing")
    request = urllib.request.Request("https://api.github.com/repos/" + REPO + path,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "phase3-read-only-snapshot"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404 and optional:
            return None
        raise Stop("GitHub read failed: HTTP " + str(error.code)) from None


def bounded(path, key=None):
    result = api(path)
    if key:
        check(isinstance(result, dict) and isinstance(result.get(key), list),
              "GitHub collection schema changed: " + path)
        result = result[key]
    check(isinstance(result, list) and len(result) < 100,
          "GitHub collection exceeds one-page bound: " + path)
    return result


def collect():
    sha = os.environ.get("PHASE3_INSTALL_SHA", "")
    check(re.fullmatch("[0-9a-f]{40}", sha) is not None,
          "no reviewed installation gate")
    check(os.environ.get("GITHUB_WORKFLOW_SHA") == sha and
          os.environ.get("GITHUB_REPOSITORY") == REPO and
          os.environ.get("GITHUB_REF") == "refs/heads/main" and
          os.environ.get("GITHUB_RUN_ATTEMPT") == "1",
          "wrong execution identity")
    comments = bounded("/issues/10/comments?per_page=100")
    issues = [api("/issues/" + str(t[0])) for t in TASKS]
    prs = bounded("/pulls?state=all&per_page=100")
    evidence = {}
    branch_refs = {}
    for _, task_id, source in TASKS:
        branch = "codex/phase3-" + task_id
        ref = api("/git/ref/heads/" + quote(branch, safe="/"), optional=True)
        branch_refs[task_id] = (ref.get("object") or {}).get("sha") if ref else None
        matches = [p for p in prs if p.get("head", {}).get("ref") == branch]
        if len(matches) == 1:
            pr = matches[0]
            number = pr["number"]
            head = pr["head"]["sha"]
            check(re.fullmatch("[0-9a-f]{40}", head) is not None,
                  "invalid PR SHA")
            evidence[task_id] = {
                "files": bounded("/pulls/" + str(number) + "/files?per_page=100"),
                "checks": bounded("/commits/" + head + "/check-runs?per_page=100",
                                  key="check_runs"),
                "runs": bounded("/actions/workflows/ci.yml/runs?event=pull_request&head_sha=" + head + "&per_page=100",
                                key="workflow_runs"),
                "reviews": bounded("/pulls/" + str(number) + "/reviews?per_page=100"),
            }
            # Reconcile one previous independent finding against the current
            # exact head. A repaired PR must preserve the original CI success.
            prior = [r for r in evidence[task_id]["reviews"]
                     if r.get("commit_id") != head and
                     "```phase3-review" in (r.get("body") or "")]
            check(len(prior) <= 1, "multiple historic reviewed heads")
            if prior:
                original = prior[0].get("commit_id", "")
                check(re.fullmatch("[0-9a-f]{40}", original) is not None,
                      "historic review head invalid")
                evidence[task_id]["repair_proof"] = api("/compare/" + original + "..." + head)
                evidence[task_id]["original_ci"] = {
                    "checks": bounded("/commits/" + original + "/check-runs?per_page=100", key="check_runs"),
                    "runs": bounded("/actions/workflows/ci.yml/runs?event=pull_request&head_sha=" + original + "&per_page=100",
                                    key="workflow_runs")
                }
    # The standalone preflight does not impersonate a paid chain run. When a
    # reviewed chain is installed, its callers can opt in to one-run admission.
    chain_run_id = os.environ.get("PHASE3_CHAIN_RUN_ID")
    chain_runs = []
    if chain_run_id:
        chain_runs = bounded("/actions/workflows/phase3-chain.yml/runs?event=workflow_dispatch&per_page=100",
                             key="workflow_runs")
    return dict(install_sha=sha, workflow_sha=sha,
        repository=REPO, ref="refs/heads/main", run_attempt=1,
        current_run_id=chain_run_id,
        chain_runs=chain_runs,
        branch_refs=branch_refs, approval_comments=comments,
        issues=issues, pull_requests=prs, evidence=evidence)


def main():
    snapshot = collect()
    decision = decide(snapshot)
    print(json.dumps(decision, sort_keys=True))
    # Read-only. Never dispatch or write an approval, branch, or PR from here.
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf8") as output:
            for name, value in decision.items():
                if name in ("action", "task", "issue", "source", "branch", "pr", "head", "reason"):
                    output.write(name + "=" + str(value) + "\n")


if __name__ == "__main__":
    try:
        main()
    except (Stop, KeyError, TypeError, ValueError, urllib.error.URLError) as error:
        raise SystemExit("STOP: " + str(error))
