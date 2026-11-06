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
    snapshot = {"issues": {}, "pulls": [], "evidence": {}}
    for item in BASE["tasks"]:
        number, head = item["receipt"]["pr"], item["receipt"]["head"]
        snapshot["issues"][str(item["issue"])] = {
            "number": item["issue"], "state": "open"}
        snapshot["pulls"].append({
            "number": number, "draft": True, "state": "open",
            "head": {"ref": q.branch_for(item), "sha": head},
            "base": {"ref": "main"}})
        review = {"task": item["id"], "head": head,
                  "verdict": "clean", "findings": []}
        snapshot["evidence"][str(number)] = {
            "checks": [{"name": "synthetic-tests", "head_sha": head,
                        "status": "completed", "conclusion": "success",
                        "app": {"slug": "github-actions"}}],
            "reviews": [{"commit_id": head, "state": "COMMENTED",
                         "body": "\x60\x60\x60phase3-review\n" +
                                 json.dumps(review) + "\n\x60\x60\x60"}]}
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
        "head": {"ref": q.branch_for(item), "sha": head},
        "base": {"ref": "main"}})
    snap["evidence"][str(number)] = {"checks": [], "reviews": []}
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
        payload = {"task": "pilot-next-v1", "head": head, "verdict": "findings"}
        snap["evidence"][str(number)]["reviews"] = [{
            "commit_id": head, "state": "COMMENTED",
            "body": "\x60\x60\x60phase4-review\n" + json.dumps(payload) + "\n\x60\x60\x60"}]
        self.assertEqual(q.decide(manifest, snap)["action"], "READY_REPAIR")
        payload["verdict"] = "clean"
        snap["evidence"][str(number)]["reviews"][0]["body"] = (
            "\x60\x60\x60phase4-review\n" + json.dumps(payload) + "\n\x60\x60\x60")
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
                       "src/../unsafe.mjs", "src//bad.mjs"):
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

    def test_no_github_mutations_in_selector(self):
        source = (ROOT / "scripts/phase4_queue.py").read_text()
        self.assertNotIn("urllib.request.Request(url, data=", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("workflow_dispatch", source)


if __name__ == "__main__":
    unittest.main()
