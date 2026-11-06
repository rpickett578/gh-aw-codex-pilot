"""Offline proof for durable queue ordering, receipts and safe recovery states."""
import json
from pathlib import Path
import sys
import unittest
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_queue as q

BASE = json.loads((ROOT / "phase4/queue.json").read_text(encoding="utf-8"))


def pending(number=19, ident="pilot-next-v1"):
    return {"id": ident, "issue": number,
            "allowed_files": ["src/" + ident + ".mjs"],
            "max_ai_credits": 40}


def fake():
    snapshot = {"issues": {}, "pulls": [], "evidence": {}, "runs": {}}
    for item in BASE["tasks"]:
        number, head = item["receipt"]["pr"], item["receipt"]["head"]
        snapshot["issues"][str(item["issue"])] = {
            "number": item["issue"], "state": "open"}
        snapshot["pulls"].append({
            "number": number, "draft": True, "state": "open",
            "head": {"ref": q.branch_for(item), "sha": head,
                     "repo": {"full_name": q.REPO}},
            "base": {"ref": "main", "repo": {"full_name": q.REPO}},
            "user": {"login": "rpickett578", "id": 313606620}})
        run_id = "42280771454" if number == 15 else "42292697441"
        snapshot["runs"][run_id] = {
            "repository": {"full_name": q.REPO}, "event": "workflow_dispatch",
            "run_attempt": 1, "status": "completed", "conclusion": "success",
            "path": ".github/workflows/phase3-chain.yml",
            "actor": {"login": "rpickett578", "id": 313606620}}
        review = {"task": item["id"], "head": head,
                  "verdict": "clean", "findings": [],
                  "install_sha": ("5580a4a864f9b6c33433a91ab354d7d6c2a92a28"
                      if number == 15 else "d004619d1e41cee6d140101a7aad254a23615ae6")}
        body = ("\x60\x60\x60phase3-review\n" + json.dumps(review) +
                "\n\x60\x60\x60\n" +
                "<!-- gh-aw-agentic-workflow: Phase3 Review, id: " + run_id +
                ", workflow_id: phase3-review, run: https://github.com/" +
                q.REPO + "/actions/runs/" + run_id + " -->\n" +
                '[gh-aw-workflow-call-id]: # "rpickett578%2Fgh-aw-codex-pilot%2Fphase3-review"')
        snapshot["evidence"][str(number)] = {
            "checks": [{"name": "synthetic-tests", "head_sha": head,
                        "status": "completed", "conclusion": "success",
                        "app": {"slug": "github-actions"}}],
            "files": [{"filename": item["allowed_files"][0], "status": "modified"}],
            "ci_runs": [{"head_sha": head, "path": ".github/workflows/ci.yml",
                        "event": "pull_request", "run_attempt": 1,
                        "status": "completed", "conclusion": "success"}],
            "reviews": [{"commit_id": head, "state": "COMMENTED",
                         "user": {"login": "github-actions[bot]", "id": 41898282},
                         "body": body}]}
    return snapshot


def with_pending():
    queue = deepcopy(BASE)
    snap = fake()
    item = pending()
    queue["tasks"].append(item)
    snap["issues"][str(item["issue"])] = {
        "number": item["issue"], "state": "open"}
    return queue, snap


def add_pr(queue, snap):
    item = queue["tasks"][-1]
    head = "f" * 40
    number = 25
    snap["pulls"].append({
        "number": number, "draft": True, "state": "open",
        "head": {"ref": q.branch_for(item), "sha": head, "repo": {"full_name": q.REPO}},
        "base": {"ref": "main", "repo": {"full_name": q.REPO}},
        "user": {"login": "rpickett578", "id": 313606620}})
    snap["evidence"][str(number)] = {
        "checks": [], "reviews": [], "files": [
            {"filename": item["allowed_files"][0], "status": "modified"}],
        "ci_runs": [{"head_sha": head, "path": ".github/workflows/ci.yml",
                    "event": "pull_request", "run_attempt": 1,
                    "status": "completed", "conclusion": "success"}]}
    return number, head


class QueueTests(unittest.TestCase):
    def test_completed_history_is_not_relaunched(self):
        self.assertEqual(q.decide(BASE, fake()),
                         {"action": "QUEUE_EMPTY", "completed": 3, "total": 3})

    def test_next_approved_item_is_selected_in_order(self):
        manifest, snap = with_pending()
        r = q.decide(manifest, snap)
        self.assertEqual((r["action"], r["task"], r["issue"], r["max_ai_credits"]),
                         ("READY_CODING", "pilot-next-v1", 19, 40))
        manifest["tasks"].append(pending(20, "pilot-later-v1"))
        snap["issues"]["20"] = {"number": 20, "state": "open"}
        self.assertEqual(q.decide(manifest, snap)["issue"], 19)

    def test_published_pr_waits_for_ci_then_review(self):
        manifest, snap = with_pending()
        number, head = add_pr(manifest, snap)
        self.assertEqual(q.decide(manifest, snap)["action"], "WAIT_CI")
        snap["evidence"][str(number)]["checks"].append({
            "name": "synthetic-tests", "head_sha": head,
            "status": "completed", "conclusion": "success",
            "app": {"slug": "github-actions"}})
        self.assertEqual(q.decide(manifest, snap)["action"], "READY_REVIEW")
        payload = {"task": "pilot-next-v1", "head": head, "verdict": "findings",
                   "findings": [{"input": "bad", "expected": {"value": "good"},
                                 "line": 1, "reason": "wrong output"}]}
        run_id = "900001"
        snap["runs"][run_id] = {
            "repository": {"full_name": q.REPO}, "event": "workflow_dispatch",
            "run_attempt": 1, "status": "completed", "conclusion": "success",
            "path": ".github/workflows/phase4-chain.yml",
            "actor": {"login": "rpickett578", "id": 313606620}}
        review_body = ("\x60\x60\x60phase4-review\n" + json.dumps(payload) +
              "\n\x60\x60\x60\n"
              "<!-- gh-aw-agentic-workflow: Phase4 Review, id: 900001, "
              "workflow_id: phase4-review, run: https://github.com/" +
              q.REPO + "/actions/runs/900001 -->\n"
              '[gh-aw-workflow-call-id]: # "rpickett578%2Fgh-aw-codex-pilot%2Fphase4-review"')
        snap["evidence"][str(number)]["reviews"] = [{
            "commit_id": head, "state": "COMMENTED",
            "user": {"login": "github-actions[bot]", "id": 41898282},
            "body": review_body}]
        self.assertEqual(q.decide(manifest, snap)["action"], "READY_REPAIR")
        payload["verdict"] = "clean"
        payload["findings"] = []
        snap["evidence"][str(number)]["reviews"][0]["body"] = (
            review_body.replace(json.dumps({"task": "pilot-next-v1", "head": head,
            "verdict": "findings", "findings": [{"input": "bad",
              "expected": {"value": "good"}, "line": 1,
              "reason": "wrong output"}]}), json.dumps(payload)))
        self.assertEqual(q.decide(manifest, snap)["action"], "QUEUE_EMPTY")

    def test_old_receipt_cannot_be_modified_or_replayed(self):
        snap = fake()
        snap["pulls"][0]["head"]["sha"] = "e" * 40
        with self.assertRaises(q.QueueError):
            q.decide(BASE, snap)
        snap = fake()
        snap["pulls"].pop(0)
        with self.assertRaises(q.QueueError):
            q.decide(BASE, snap)

    def test_failed_or_foreign_ci_blocks(self):
        manifest, snap = with_pending()
        number, head = add_pr(manifest, snap)
        checks = snap["evidence"][str(number)]["checks"]
        checks.append({"name": "synthetic-tests", "head_sha": head,
                       "status": "completed", "conclusion": "failure",
                       "app": {"slug": "github-actions"}})
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)
        checks[0]["conclusion"] = "success"
        checks[0]["app"]["slug"] = "unknown"
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)

    def test_duplicate_and_overlapping_queue_entries_blocked(self):
        manifest, snap = with_pending()
        manifest["tasks"].append(deepcopy(manifest["tasks"][-1]))
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)
        manifest["tasks"][-1]["id"] = "different-v1"
        manifest["tasks"][-1]["issue"] = 20
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)

    def test_hidden_or_parent_paths_and_unbudgeted_tasks_rejected(self):
        for source in ("../secret.txt", ".github/workflows/ci.yml",
                       "src/../unsafe.mjs", "src//bad.mjs",
                       "test/fixture.test.mjs", "docs/tamper.md"):
            manifest, _ = with_pending()
            manifest["tasks"][-1]["allowed_files"] = [source]
            with self.assertRaises(q.QueueError):
                q.validate(manifest)
        manifest, _ = with_pending()
        manifest["tasks"][-1]["max_ai_credits"] = 0
        with self.assertRaises(q.QueueError):
            q.validate(manifest)

    def test_missing_or_closed_issue_blocks(self):
        manifest, snap = with_pending()
        snap["issues"]["19"]["state"] = "closed"
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)

    def test_pr_identity_mismatch_and_double_branch_block(self):
        manifest, snap = with_pending()
        number, _ = add_pr(manifest, snap)
        snap["pulls"][-1]["draft"] = False
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)
        snap["pulls"][-1]["draft"] = True
        snap["pulls"].append(deepcopy(snap["pulls"][-1]))
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)

    def test_extra_or_unauthorized_pr_file_never_passes(self):
        manifest, snap = with_pending()
        number, head = add_pr(manifest, snap)
        snap["evidence"][str(number)]["files"].append(
            {"filename": "test/unsafe.test.mjs", "status": "added"})
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)

    def test_fork_or_wrong_publisher_never_passes(self):
        manifest, snap = with_pending()
        add_pr(manifest, snap)
        snap["pulls"][-1]["head"]["repo"]["full_name"] = "someone/foreign"
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)
        snap["pulls"][-1]["head"]["repo"]["full_name"] = q.REPO
        snap["pulls"][-1]["user"]["id"] = 123
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)

    def test_untrusted_review_cannot_mark_completed(self):
        snap = fake()
        first = BASE["tasks"][0]["receipt"]["pr"]
        snap["evidence"][str(first)]["reviews"][0]["user"]["id"] = 17
        with self.assertRaises(q.QueueError):
            q.decide(BASE, snap)
        snap = fake()
        snap["evidence"][str(first)]["reviews"][0]["body"] = (
            snap["evidence"][str(first)]["reviews"][0]["body"]
            .replace("workflow_id: phase3-review", "workflow_id: forged-review"))
        with self.assertRaises(q.QueueError):
            q.decide(BASE, snap)

    def test_untrusted_ci_workflow_run_cannot_mark_completed(self):
        snap = fake()
        first = BASE["tasks"][0]["receipt"]["pr"]
        snap["evidence"][str(first)]["ci_runs"][0]["path"] = (
            ".github/workflows/forged-ci.yml")
        with self.assertRaises(q.QueueError):
            q.decide(BASE, snap)
        snap = fake()
        snap["evidence"][str(first)]["ci_runs"][0]["conclusion"] = "failure"
        with self.assertRaises(q.QueueError):
            q.decide(BASE, snap)

    def test_ref_qualified_github_workflow_paths_are_genuine(self):
        snap = fake()
        for detail in snap["evidence"].values():
            detail["ci_runs"][0]["path"] = ".github/workflows/ci.yml@refs/pull/15/merge"
        for run in snap["runs"].values():
            run["path"] = ".github/workflows/phase3-chain.yml@main"
        self.assertEqual(q.decide(BASE, snap)["action"], "QUEUE_EMPTY")
        self.assertFalse(q.workflow_path_is(".github/workflows/ci.yml.backup@main",
                                             ".github/workflows/ci.yml"))
        self.assertFalse(q.workflow_path_is(".github/workflows/ci.yml@../wrong",
                                             ".github/workflows/ci.yml"))

    def test_receipt_does_not_change_future_task_branch(self):
        item = pending(21, "my-future-v1")
        old_branch = q.branch_for(item)
        item["receipt"] = {"pr": 42, "head": "f" * 40}
        item["max_ai_credits"] = 0
        self.assertEqual(old_branch, q.branch_for(item))
        self.assertEqual(old_branch, "codex/phase4-my-future-v1")

    def test_reject_malformed_native_review_findings(self):
        manifest, snap = with_pending()
        number, head = add_pr(manifest, snap)
        snap["evidence"][str(number)]["checks"] = [{
            "name": "synthetic-tests", "head_sha": head,
            "status": "completed", "conclusion": "success",
            "app": {"slug": "github-actions"}}]
        snap["runs"]["900001"] = {
            "repository": {"full_name": q.REPO}, "event": "workflow_dispatch",
            "run_attempt": 1, "status": "completed", "conclusion": "success",
            "path": ".github/workflows/phase4-chain.yml",
            "actor": {"login": "rpickett578", "id": 313606620}}
        data = {"task": "pilot-next-v1", "head": head,
                "verdict": "findings", "findings": [{}]}
        snap["evidence"][str(number)]["reviews"] = [{
            "commit_id": head, "state": "COMMENTED",
            "user": {"login": "github-actions[bot]", "id": 41898282},
            "body": ("\x60\x60\x60phase4-review\n" + json.dumps(data) +
                     "\n\x60\x60\x60\n"
                     "<!-- gh-aw-agentic-workflow: Phase4 Review, id: 900001, "
                     "workflow_id: phase4-review, run: https://github.com/" +
                     q.REPO + "/actions/runs/900001 -->\n"
                     '[gh-aw-workflow-call-id]: # "rpickett578%2Fgh-aw-codex-pilot%2Fphase4-review"')}]
        with self.assertRaises(q.QueueError):
            q.decide(manifest, snap)

    def test_no_github_mutations_in_selector(self):
        source = (ROOT / "scripts/phase4_queue.py").read_text()
        self.assertNotIn("urllib.request.Request(url, data=", source)
        self.assertNotIn("subprocess", source)
        # Reading a workflow_dispatch run's event is not dispatching one.
        self.assertNotIn('method="POST"', source)
        self.assertNotIn('method="PATCH"', source)
        self.assertNotIn('method="PUT"', source)
        self.assertNotIn('method="DELETE"', source)


if __name__ == "__main__":
    unittest.main()
