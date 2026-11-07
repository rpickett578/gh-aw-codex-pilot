"""Zero-network tests for Phase4 reusable paid-worker admission and commit guard."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_runtime as rt

SHA = "a" * 40
HEAD = "b" * 40


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.context = Path(self.temp.name) / "phase4-context.json"
        self.manifest = Path(self.temp.name) / "queue.json"
        self.manifest.write_text(json.dumps({
            "version": 1,
            "repository": rt.REPO,
            "tasks": [{"id": "pilot-next-v1", "issue": 21,
                       "allowed_files": ["src/pilot-next-v1.mjs"],
                       "max_ai_credits": 60}]}))
        self.environ = patch.dict(os.environ, {
            "GITHUB_REPOSITORY": rt.REPO,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW_SHA": SHA,
            "GITHUB_RUN_ID": "9000",
            "PHASE4_TASK_ID": "pilot-next-v1",
            "PHASE4_ACTION": "READY_CODING",
            "PHASE4_ISSUE": "21",
            "PHASE4_SOURCE": "src/pilot-next-v1.mjs",
            "PHASE4_QUEUE_PATH": str(self.manifest),
            "PHASE4_HEAD": HEAD,
            "PHASE4_PR": "99",
        })
        self.environ.start()
        self.addCleanup(self.environ.stop)
        self.patches = [
            patch.object(rt, "CONTEXT", self.context),
            patch.object(rt, "get", return_value={"commit": {"sha": SHA}}),
            patch.object(rt, "live_snapshot", return_value={
                "issues": {"21": {"number": 21, "state": "open",
                                  "body": "Implement one inert source"}}}),
            patch.object(rt, "decide", return_value={
                "action": "READY_CODING", "task": "pilot-next-v1",
                "issue": 21, "index": 0, "max_ai_credits": 60,
                "pr": None}),
            patch.object(rt, "sh", return_value=SHA),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_admit_one_approved_task(self):
        data = rt.admit()
        self.assertEqual(data["task"], "pilot-next-v1")
        self.assertEqual(data["source"], "src/pilot-next-v1.mjs")
        self.assertEqual(data["action"], "READY_CODING")
        self.assertTrue(self.context.is_file())

    def test_recheck_does_not_require_git_checkout(self):
        with patch.object(rt, "sh", side_effect=AssertionError("no checkout expected")):
            self.assertEqual(rt.admit(verify_checkout=False)["issue"], 21)

    def test_reject_noncurrent_task_and_stale_main(self):
        with patch.dict(os.environ, {"PHASE4_TASK_ID": "unapproved-task"}):
            with self.assertRaises(rt.QueueError):
                rt.admit()
        with patch.object(rt, "get", return_value={"commit": {"sha": HEAD}}):
            with self.assertRaises(rt.QueueError):
                rt.admit()

    def test_reject_broader_or_wrong_publisher_source(self):
        for path in ("src/**", "src/unrelated.mjs", "test/forged.test.mjs"):
            with self.subTest(path=path):
                with patch.dict(os.environ, {"PHASE4_SOURCE": path}):
                    with self.assertRaises(rt.QueueError):
                        rt.admit()

    def test_reject_stale_reviewer_sha(self):
        with patch.dict(os.environ, {"PHASE4_ACTION": "READY_REVIEW"}):
            with patch.object(rt, "decide", return_value={
                    "action": "READY_REVIEW", "task": "pilot-next-v1",
                    "issue": 21, "index": 0, "max_ai_credits": 60, "pr": 99}):
                pulls = [{"number": 99, "head": {"sha": "c" * 40}}]
                with patch.object(rt, "live_snapshot", return_value={
                    "issues": {"21": {"number": 21, "state": "open",
                                      "body": "Implement one inert source"}},
                    "pulls": pulls}):
                    with self.assertRaises(rt.QueueError):
                        rt.admit(verify_checkout=False)
                    pulls[0]["head"]["sha"] = HEAD
                    self.assertEqual(rt.admit(verify_checkout=False)["head"], HEAD)

    def test_enforce_stage_cost_envelope(self):
        with patch.object(rt, "decide", return_value={
                "action": "READY_CODING", "task": "pilot-next-v1",
                "issue": 21, "index": 0, "max_ai_credits": 15}):
            with self.assertRaises(rt.QueueError):
                rt.admit()

    def test_one_exact_approved_source_commit(self):
        rt.admit()
        values = {
            ("rev-parse", "HEAD"): HEAD,
            ("rev-parse", "HEAD^"): SHA,
            ("diff", "--name-only", SHA, HEAD): "src/pilot-next-v1.mjs",
            ("status", "--porcelain"): "",
        }
        with patch.object(rt, "sh", side_effect=lambda *args: values[args]):
            rt.post()
        values[("diff", "--name-only", SHA, HEAD)] = "test/forged.test.mjs"
        with patch.object(rt, "sh", side_effect=lambda *args: values[args]):
            with self.assertRaises(rt.QueueError):
                rt.post()


if __name__ == "__main__":
    unittest.main()
