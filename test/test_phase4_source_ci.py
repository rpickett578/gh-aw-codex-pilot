"""No-network tests for generic approved Phase4 source PR verification."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_source_ci as c
from phase4_queue import QueueError, REPO


def approved_manifest():
    return {"version": 1, "repository": REPO,
            "tasks": [{"id": "count-ascii-digits-v1",
                       "issue": 23,
                       "allowed_files": ["src/count-ascii-digits-v1.mjs"],
                       "max_ai_credits": 53}]}


class SourceCITests(unittest.TestCase):
    def test_queued_task_gets_exact_protected_fixture(self):
        task, test = c.approved_task(approved_manifest(),
                                     "codex/phase4-count-ascii-digits-v1")
        self.assertEqual(task["allowed_files"], ["src/count-ascii-digits-v1.mjs"])
        self.assertEqual(test, "test/count-ascii-digits-v1.test.mjs")

    def test_unknown_task_branch_fails(self):
        for branch in ("codex/phase4-unapproved",
                       "codex/phase4-../escape", "codex/phase3-count-ascii-digits-v1",
                       "codex/phase4-", "codex/phase4-Caps"):
            with self.subTest(branch=branch), self.assertRaises(QueueError):
                c.approved_task(approved_manifest(), branch)

    def test_bad_budget_or_completed_receipt_fails(self):
        manifest = approved_manifest()
        manifest["tasks"][0]["max_ai_credits"] = 52
        with self.assertRaises(QueueError):
            c.approved_task(manifest, "codex/phase4-count-ascii-digits-v1")
        manifest["tasks"][0]["max_ai_credits"] = 0
        manifest["tasks"][0]["receipt"] = {"pr": 99, "head": "a" * 40}
        with self.assertRaises(QueueError):
            c.approved_task(manifest, "codex/phase4-count-ascii-digits-v1")

    def test_unapproved_path_or_extra_file_fails(self):
        path = "src/count-ascii-digits-v1.mjs"
        for changed in ([], [path, "test/forged.test.mjs"],
                        ["src/unrelated.mjs"], ["scripts/phase4_source_ci.py"]):
            with self.subTest(paths=changed), self.assertRaises(QueueError):
                c.validate_changed_files(path, changed)
        c.validate_changed_files(path, [path])

    def test_multiple_task_files_fail(self):
        manifest = approved_manifest()
        manifest["tasks"][0]["allowed_files"].append("src/other.mjs")
        with self.assertRaises(QueueError):
            c.approved_task(manifest, "codex/phase4-count-ascii-digits-v1")

    def test_identity_guard_blocks_other_repository(self):
        with patch.dict(c.os.environ, {
            "REPOSITORY": "somewhere/else",
            "HEAD_REPOSITORY": REPO,
            "BASE_SHA": "a" * 40,
            "HEAD_SHA": "b" * 40,
            "HEAD_BRANCH": "codex/phase4-count-ascii-digits-v1"}):
            with self.assertRaises(QueueError):
                c.verify()


if __name__ == "__main__":
    unittest.main()
