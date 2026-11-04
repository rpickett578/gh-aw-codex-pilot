"""Admission and evidence checks for Issue #3; never dispatches or mutates GitHub."""
import base64
from datetime import datetime
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
import zipfile
from pathlib import Path

REPO = "rpickett578/gh-aw-codex-pilot"
HEAD = "f50e1a8ccc84cee5812c31938a31c93a078e7103"
BRANCH = "codex/pilotfix/ascii-slug-normalization-58cc9ff5c8519ae2"
TASK = "reverse-ascii-v1"
NEXT_BRANCH = "codex/phase2-reverse-ascii-v1"
KEY = "phase2-2-" + HEAD + "-" + TASK
RECOVERY_V1_KEY = KEY + "-recovery-v1"
RECOVERY_V2_KEY = KEY + "-recovery-v2"
RECOVERY_KEY = KEY + "-recovery-v3"
FAILED_RUN = 41880752255
FAILED_SHA = "fa995cbf91f4e7d02916e35f0fd8f9979a8ad298"
CONSUMED_RECOVERY_RUN = 41891536813
CONSUMED_RECOVERY_SHA = "40ebfd180e4285167d62e9d0ce680b73af5a1116"
CONSUMED_V2_RUN = 41901264550
CONSUMED_V2_SHA = "b876867631bc89c7b5775c98c72f1b44a16c963f"
SOURCE = "src/slugify.mjs"
NEXT_SOURCE = "src/reverse-ascii.mjs"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def api(path, missing=False):
    require(path.startswith("/"), "repository-relative API path required")
    request = urllib.request.Request("https://api.github.com/repos/" + REPO + path,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json", "User-Agent": "phase2-admission"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if missing and error.code == 404:
            return None
        raise ValueError("GitHub read failed, HTTP " + str(error.code)) from None


def validate_pr(pr, sha):
    require(pr["number"] == 2 and pr["state"] == "open" and pr["draft"], "PR #2 must remain open and Draft")
    require(pr["head"]["repo"]["full_name"] == REPO and pr["base"]["repo"]["full_name"] == REPO,
            "fork or repository mismatch")
    require(pr["head"]["ref"] == BRANCH and pr["base"]["ref"] == "main", "branch mismatch")
    require(pr["head"]["sha"] == sha, "PR head changed")


def oracle(value):
    if not isinstance(value, str):
        return {"error": "TypeError"}
    return {"value": re.sub(r"[^a-z0-9]+", "-", re.sub(r"[A-Z]", lambda m: m[0].lower(), value)).strip("-")}


def validate_review(review, run_id):
    require(review["state"] == "COMMENTED" and review["commit_id"] == HEAD,
            "review must be COMMENT on original exact head")
    require(review["user"]["login"] == "github-actions[bot]" and review["user"]["id"] == 41898282
            and review["user"]["type"] == "Bot", "unexpected reviewer identity")
    require(type(review["id"]) is int and review["id"] > 0, "invalid review ID")
    require(review["html_url"] == f"https://github.com/{REPO}/pull/2#pullrequestreview-{review['id']}", "review URL differs")
    marker = f"id: {run_id}, workflow_id: phase2-review, run: https://github.com/{REPO}/actions/runs/{run_id}"
    require(marker in review["body"] and f'"rpickett578%2Fgh-aw-codex-pilot%2Fphase2-review"' in review["body"],
            "native workflow publication marker missing")
    blocks = re.findall(r"```phase2-review\s*\n(.*?)\n```", review["body"], re.S)
    require(len(blocks) == 1, "exactly one structured review block required")
    data = json.loads(blocks[0])
    require(set(data) == {"run_id", "head", "verdict", "findings"}, "review schema differs")
    require(data["run_id"] == str(run_id) and data["head"] == HEAD, "review provenance differs")
    findings = data["findings"]
    require(isinstance(findings, list) and len(findings) <= 3, "at most three findings")
    require(data["verdict"] in ["clean", "findings"], "unknown review disposition")
    require((data["verdict"] == "clean") == (len(findings) == 0), "inconsistent disposition")
    for finding in findings:
        require(set(finding) == {"input", "expected", "line", "reason"}, "finding schema differs")
        require(len(json.dumps(finding["input"])) <= 256, "finding input too large")
        require(finding["expected"] == oracle(finding["input"]), "finding contradicts TASK.md")
        require(type(finding["line"]) is int and 1 <= finding["line"] <= 10, "invalid source line")
        require(isinstance(finding["reason"], str) and 1 <= len(finding["reason"]) <= 1000, "missing bounded reason")
    return data


def validate_publication(review, run, jobs, items):
    """Authenticate a publication; a historical authentic review is not a recovery admission."""
    run_id = str(run["id"])
    validate_review(review, run_id)
    require(run["event"] == "workflow_dispatch" and run["path"] == ".github/workflows/phase2-chain.yml"
            and run["run_attempt"] == 1 and run["actor"]["login"] == "rpickett578", "publication run differs")
    publishers = [j for j in jobs if j["name"] == "review / safe_outputs"]
    require(publishers, "publisher job metadata not yet visible")
    require(len(publishers) == 1, "publisher job ambiguous")
    job = publishers[0]
    require(job["run_id"] == run["id"] and job["head_sha"] == run["head_sha"], "publisher identity differs")
    require(job["status"] == "completed", "publisher metadata not yet complete")
    require(job["conclusion"] == "success", "publisher failed")
    submitted = datetime.fromisoformat(review["submitted_at"].replace("Z", "+00:00"))
    require(datetime.fromisoformat(job["started_at"].replace("Z", "+00:00")) <= submitted <=
            datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00")), "review outside publisher interval")
    matches = [i for i in items if i.get("type") == "submit_pull_request_review" and i.get("id") == review["id"]]
    require(len(matches) == 1, "native publication manifest missing or ambiguous")
    item = matches[0]
    require(item["status"] == "success" and item["repo"] == REPO and item["number"] == 2
            and item["url"] == review["html_url"] and item["metadata"]["review_id"] == review["id"]
            and item["metadata"]["review_event"] == "COMMENT" and item["metadata"]["review_state"] == "COMMENTED",
            "native publication manifest differs")


def publication_items(run_id):
    # Only official native publisher artifacts from the exact root run; no extraction or code execution.
    data = api(f"/actions/runs/{run_id}/artifacts?per_page=100")
    require(data["total_count"] < 100, "artifact inventory exceeds bound")
    artifacts = [a for a in data["artifacts"] if a["name"].endswith("-safe-outputs-items")]
    require(artifacts, "publication artifact not yet visible")
    require(len(artifacts) <= 3, "publication artifacts ambiguous")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    rows = []
    for artifact in artifacts:
        require(not artifact["expired"] and artifact["size_in_bytes"] <= 131072, "publication artifact unavailable or oversized")
        request = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact['id']}/zip",
            headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "User-Agent": "phase2-publication"})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=30):
                raise ValueError("expected GitHub artifact redirect")
        except urllib.error.HTTPError as error:
            try:
                require(error.code == 302, "artifact redirect failed")
                location = error.headers["Location"]
            finally:
                error.close()
        parsed = urlparse(location)
        require(parsed.scheme == "https" and parsed.hostname and
                (parsed.hostname.endswith(".blob.core.windows.net") or parsed.hostname.endswith(".githubusercontent.com")),
                "untrusted artifact download host")
        # Fresh request deliberately has NO Authorization header on the cross-host signed URL.
        try:
            with urllib.request.urlopen(urllib.request.Request(location), timeout=30) as response:
                archive = response.read(131073)
            require(len(archive) <= 131072, "artifact exceeds download bound")
            with zipfile.ZipFile(io.BytesIO(archive)) as package:
                info = package.getinfo("safe-output-items.jsonl")
                require(info.file_size <= 262144, "manifest exceeds decompression bound")
                rows.extend(json.loads(line) for line in package.read(info).decode().splitlines() if line.strip())
        except (OSError, KeyError, zipfile.BadZipFile) as error:
            raise ValueError("native artifact download or decoding failed") from None
    return rows


def _read_review_evidence():
    rows = api("/pulls/2/reviews?per_page=100")
    require(len(rows) < 100, "review history exceeds bounded scan")
    selected = []
    for review in rows:
        if "```phase2-review" not in (review.get("body") or ""):
            continue
        current = re.search(r'"run_id"\s*:\s*"' + re.escape(os.environ["GITHUB_RUN_ID"]) + r'"', review["body"])
        if not current:
            continue
        # Historical reviews are ignored; a review claiming THIS run must validate,
        # rather than disguising a forged author or payload as propagation delay.
        evidence = validate_review(review, os.environ["GITHUB_RUN_ID"])
        selected.append((review, evidence))
    require(selected, "current-run review not yet visible")
    require(len(selected) == 1, "current-run review ambiguous")
    review, evidence = selected[0]
    expected_id = os.environ.get("REVIEW_ID")
    require(not expected_id or str(review["id"]) == expected_id, "review ID changed")
    run = api("/actions/runs/" + os.environ["GITHUB_RUN_ID"])
    require(run["head_sha"] == os.environ["GITHUB_WORKFLOW_SHA"] and run["display_title"] == RECOVERY_KEY,
            "review is not from this recovery installation")
    job_data = api(f"/actions/runs/{run['id']}/jobs?per_page=100")
    require(job_data["total_count"] < 100, "publisher job inventory exceeds bound")
    validate_publication(review, run, job_data["jobs"], publication_items(run["id"]))
    return review, evidence


def review_evidence(wait=False):
    # Native publication can finish before its REST projections catch up. Read-only
    # admission polling never reruns a job, inference, review submission or CI.
    pending = {"current-run review not yet visible", "publisher job metadata not yet visible",
               "publisher metadata not yet complete", "publication artifact not yet visible"}
    for attempt in range(13 if wait else 1):
        try:
            return _read_review_evidence()
        except ValueError as error:
            if not wait or str(error) not in pending or attempt == 12:
                raise
            time.sleep(10)


def source_at(sha):
    item = api("/contents/" + SOURCE + "?ref=" + sha)
    require(item["size"] <= 16384 and item["encoding"] == "base64", "source size or encoding differs")
    return base64.b64decode(item["content"])


def observe(source, value):
    # No reviewer-provided code or shell command is executed. Only a JSON input
    # reaches the synthetic function, in a process with no credential environment.
    with tempfile.TemporaryDirectory(prefix="phase2-case-") as directory:
        module = Path(directory) / "source.mjs"
        module.write_bytes(source)
        runner = """import {pathToFileURL} from 'node:url';
const {slugify}=await import(pathToFileURL(process.argv[1]));
try { console.log(JSON.stringify({value:slugify(JSON.parse(process.argv[2]))})); }
catch(e) { console.log(JSON.stringify({error:e.name})); }"""
        env = {key: os.environ[key] for key in ["PATH", "SystemRoot"] if key in os.environ}
        result = subprocess.run(["node", "--permission", "--allow-fs-read=" + str(module),
                                 "--input-type=module", "-e", runner, str(module), json.dumps(value)],
                                capture_output=True, text=True, encoding="utf-8", timeout=5, env=env)
        require(result.returncode == 0, "reproducer process failed")
        return json.loads(result.stdout)


def validate_findings(evidence, source, fixed=False):
    require(evidence["findings"], "no authentic finding; repair is NOT APPLICABLE")
    for finding in evidence["findings"]:
        matches = observe(source, finding["input"]) == finding["expected"]
        require(matches if fixed else not matches,
                "finding not resolved" if fixed else "finding does not reproduce")


def ci_success(checks, runs, sha):
    relevant = [c for c in checks if c["name"] == "synthetic-tests"]
    require(len(relevant) == 1, "required check missing or ambiguous")
    check = relevant[0]
    require(check["head_sha"] == sha and check["app"]["slug"] == "github-actions", "CI identity differs")
    require(check["status"] == "completed" and check["conclusion"] == "success", "actual required CI is not success")
    matching = [r for r in runs if r["head_sha"] == sha and r["path"] == ".github/workflows/ci.yml"]
    require(len(matching) == 1 and matching[0]["event"] == "pull_request", "CI run missing or ambiguous")
    require(matching[0]["status"] == "completed" and matching[0]["conclusion"] == "success", "CI run not successful")
    require(matching[0]["run_attempt"] == 1, "CI retry not admitted")


def actual_ci(sha, wait=False):
    for attempt in range(13 if wait else 1):
        checks = api("/commits/" + sha + "/check-runs")["check_runs"]
        runs = api("/actions/workflows/ci.yml/runs?event=pull_request&head_sha=" + sha)["workflow_runs"]
        try:
            ci_success(checks, runs, sha)
            print("Actual GitHub synthetic-tests success: " + sha)
            return
        except ValueError:
            failures = [c for c in checks if c["name"] == "synthetic-tests" and c["status"] == "completed" and c["conclusion"] != "success"]
            if failures or not wait or attempt == 12:
                raise
            time.sleep(10)  # Bounded two-minute admission wait, never reruns CI.


def output(**values):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(key + "=" + str(value) + "\n")


def one_attempt(runs, run_id, key=KEY):
    require(len(runs) < 100, "run history exceeds bounded scan")
    require(not any(r["id"] != int(run_id) and r["display_title"] == key for r in runs),
            "PR-head/task key already admitted or attempted")


def recovery_admission(runs, run_id):
    one_attempt(runs, run_id, RECOVERY_KEY)
    previous = [r for r in runs if r["id"] == FAILED_RUN]
    require(len(previous) == 1, "exact consumed original run missing")
    old = previous[0]
    require(old["display_title"] == KEY and old["head_sha"] == FAILED_SHA and old["status"] == "completed"
            and old["conclusion"] == "failure" and old["run_attempt"] == 1, "original failure provenance differs")
    prior = [r for r in runs if r["id"] == CONSUMED_RECOVERY_RUN]
    require(len(prior) == 1, "exact consumed recovery-v1 run missing")
    prior = prior[0]
    require(prior["display_title"] == RECOVERY_V1_KEY and prior["head_sha"] == CONSUMED_RECOVERY_SHA
            and prior["status"] == "completed" and prior["conclusion"] == "success" and prior["run_attempt"] == 1,
            "consumed recovery-v1 provenance differs")
    v2 = [r for r in runs if r["id"] == CONSUMED_V2_RUN]
    require(len(v2) == 1, "exact consumed recovery-v2 run missing")
    v2 = v2[0]
    require(v2["display_title"] == RECOVERY_V2_KEY and v2["head_sha"] == CONSUMED_V2_SHA
            and v2["status"] == "completed" and v2["conclusion"] == "failure" and v2["run_attempt"] == 1,
            "consumed recovery-v2 provenance differs")
    require(all(r["id"] in [FAILED_RUN, CONSUMED_RECOVERY_RUN, CONSUMED_V2_RUN, int(run_id)] for r in runs), "another Phase 2 attempt exists")
    current = [r for r in runs if r["id"] == int(run_id)]
    require(len(current) == 1 and current[0]["display_title"] == RECOVERY_KEY
            and current[0]["head_sha"] == os.environ["GITHUB_WORKFLOW_SHA"] and current[0]["run_attempt"] == 1,
            "recovery run identity differs")


def validate_repair_head(sha, repair_sha, head_commit=None, repair_commit=None):
    require(re.fullmatch(r"[a-f0-9]{40}", repair_sha), "trusted repair output SHA missing")
    if sha != repair_sha:
        require(len(head_commit["parents"]) == 1 and head_commit["parents"][0]["sha"] == repair_sha,
                "head is not the native repair output or its CI trigger commit")
        require(head_commit["commit"]["tree"]["sha"] == repair_commit["commit"]["tree"]["sha"],
                "CI trigger child is not empty")


def validate_completion(results, repair_required, number, url, cancelled):
    require(cancelled == "false", "workflow cancelled")
    require(all(results.get(job) == "success" for job in ["admit", "review", "route", "continue", "next"]),
            "mandatory Phase 2 job failed or skipped")
    require(repair_required in ["true", "false"], "repair disposition missing")
    require(results.get("repair") == ("success" if repair_required == "true" else "skipped"),
            "repair result contradicts review disposition")
    require(isinstance(number, str) and re.fullmatch(r"[1-9][0-9]*", number), "native next PR number missing")
    require(url == f"https://github.com/{REPO}/pull/{number}", "native next PR URL missing or invalid")


def accept_next_pr(number, url, pr, files, items):
    require(pr["number"] == int(number) and pr["html_url"] == url and pr["state"] == "open"
            and pr["draft"] and not pr["merged"], "next PR must exist, be Draft and remain unmerged")
    require(pr["head"]["repo"]["full_name"] == REPO == pr["base"]["repo"]["full_name"]
            and pr["head"]["ref"] == NEXT_BRANCH and pr["base"]["ref"] == "main", "next PR scope differs")
    require([f["filename"] for f in files] == [NEXT_SOURCE], "next PR changed unrelated files")
    published = [i for i in items if i.get("type") == "create_pull_request"]
    require(len(published) == 1 and published[0]["status"] == "success" and published[0]["repo"] == REPO
            and published[0]["number"] == int(number) and published[0]["url"] == url,
            "exact current-run native PR publication missing")


def entry():
    require(os.environ["GITHUB_REPOSITORY"] == REPO, "pilot repository only")
    require(os.environ["GITHUB_RUN_ATTEMPT"] == "1", "reruns forbidden")
    require(os.environ.get("PHASE2_EXECUTION_SHA") == os.environ["GITHUB_WORKFLOW_SHA"], "separate reviewed execution authorization missing")
    require(os.environ.get("PHASE2_RECOVERY_KEY") == RECOVERY_KEY, "explicit recovery-v3 admission required")
    stage = sys.argv[1]
    require(stage not in ["repair", "repair-after", "publish-repair"],
            "recovery-v3 is clean-path only; repair publication contract remains blocked")
    if stage == "accept":
        results = {job: os.environ.get(job.upper() + "_RESULT", "") for job in ["admit", "review", "route", "repair", "continue", "next"]}
        number, url = os.environ.get("NEXT_PR_NUMBER", ""), os.environ.get("NEXT_PR_URL", "")
        validate_completion(results, os.environ.get("REPAIR_REQUIRED"), number, url, os.environ.get("RUN_CANCELLED"))
        validate_pr(api("/pulls/2"), os.environ["EXPECTED_HEAD"])
        review_evidence(wait=True)
        pr = api("/pulls/" + number)
        accept_next_pr(number, url, pr, api("/pulls/" + number + "/files"), publication_items(os.environ["GITHUB_RUN_ID"]))
        actual_ci(pr["head"]["sha"], wait=True)
        print("ACCEPTED: exact native Draft PR " + url + " at " + pr["head"]["sha"])
    elif stage == "admit":
        require(os.environ["GITHUB_REF"] == "refs/heads/main", "reviewed main installation only")
        runs = api("/actions/workflows/phase2-chain.yml/runs?event=workflow_dispatch&per_page=100")["workflow_runs"]
        recovery_admission(runs, os.environ["GITHUB_RUN_ID"])
        validate_pr(api("/pulls/2"), HEAD)
        require([f["filename"] for f in api("/pulls/2/files")] == [SOURCE], "unrelated PR files")
        actual_ci(HEAD)
    elif stage in ["review", "publish-review"]:
        validate_pr(api("/pulls/2"), HEAD)
        actual_ci(HEAD)
        if stage == "review":
            Path("/tmp/gh-aw/phase2-review-context.json").write_text(
                json.dumps({"run_id": os.environ["GITHUB_RUN_ID"], "head": HEAD, "pr": 2}), encoding="utf-8")
    elif stage == "route":
        validate_pr(api("/pulls/2"), HEAD)
        review, evidence = review_evidence(wait=True)
        if evidence["findings"]:
            validate_findings(evidence, source_at(HEAD))
            raise ValueError("recovery-v3 is clean-path only; genuine findings require separate repair authorization")
        output(repair=str(bool(evidence["findings"])).lower(), review_id=review["id"])
        print("Repair: " + ("required by reproducible finding" if evidence["findings"] else "NOT APPLICABLE; clean review"))
    elif stage in ["repair", "repair-after", "publish-repair"]:
        validate_pr(api("/pulls/2"), HEAD)
        _, evidence = review_evidence()
        validate_findings(evidence, source_at(HEAD))
        Path("/tmp/gh-aw/phase2-findings.json").write_text(json.dumps(evidence), encoding="utf-8")
        if stage == "repair-after":
            validate_findings(evidence, Path(SOURCE).read_bytes(), fixed=True)
    elif stage in ["continue", "next", "publish-next"]:
        pr = api("/pulls/2")
        sha = pr["head"]["sha"]
        validate_pr(pr, sha)
        require(not os.environ.get("EXPECTED_HEAD") or sha == os.environ["EXPECTED_HEAD"], "handoff head changed")
        _, evidence = review_evidence()
        if evidence["findings"]:
            require(sha != HEAD, "repair did not change head")
            repair_sha = os.environ.get("REPAIR_SHA", "")
            if stage == "continue":
                validate_repair_head(sha, repair_sha,
                    api("/commits/" + sha) if sha != repair_sha else None,
                    api("/commits/" + repair_sha) if sha != repair_sha else None)
            compare = api("/compare/" + HEAD + "..." + sha)
            require(compare["status"] == "ahead" and 1 <= compare["ahead_by"] <= 2, "not one bounded correction")
            require([f["filename"] for f in compare["files"]] == [SOURCE], "repair touched unrelated files")
            validate_findings(evidence, source_at(HEAD))
            validate_findings(evidence, source_at(sha), fixed=True)
        else:
            require(sha == HEAD, "clean review no longer matches PR head")
        actual_ci(sha, wait=stage == "continue")
        require(api("/git/ref/heads/" + NEXT_BRANCH, missing=True) is None, "next task branch already exists")
        if stage == "publish-next":
            items = json.loads(Path(os.environ["GH_AW_AGENT_OUTPUT"]).read_text())["items"]
            coding = [item for item in items if item.get("type") == "create_pull_request"]
            require(len(coding) == 1 and coding[0].get("branch") == "phase2-reverse-ascii-v1",
                    "next task must use its fixed branch name")
        output(head_sha=sha, task_id=TASK, dedup_key=sha + ":" + TASK)
    else:
        raise ValueError("unknown phase2 stage")
    print("PASS: Phase 2 admission " + stage)


if __name__ == "__main__":
    try:
        entry()
    except (ValueError, KeyError, TimeoutError, subprocess.SubprocessError) as error:
        raise SystemExit("STOP: " + str(error))
