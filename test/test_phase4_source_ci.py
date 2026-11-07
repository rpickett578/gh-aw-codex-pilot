"""No-network tests for generic approved Phase4 source PR verification."""
from pathlib import Path
import sys
import unittest
import tempfile
import subprocess
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

    def test_fixture_expected_count_is_reviewed_metadata(self):
        import json
        metadata = json.loads((ROOT / "test/count-ascii-digits-v1.test-meta.json").read_text())
        self.assertEqual(metadata, {"expected_tests": 20})

    def test_runner_requires_exact_20_real_cases(self):
        def tap(tests, passed=None):
            return ("TAP version 13\n" +
                    "\n".join(["# tests " + str(tests),
                                "# pass " + str(tests if passed is None else passed),
                                "# fail 0", "# cancelled 0",
                                "# skipped 0", "# todo 0"]) + "\n")
        c.required_tests(tap(20), 20)
        with self.assertRaises(QueueError):
            c.required_tests(tap(1), 20)  # process.exit(0) ran no real fixture assertions
        with self.assertRaises(QueueError):
            c.required_tests(tap(20, 19), 20)
        with self.assertRaises(QueueError):
            c.required_tests(tap(20), True)
        # Printing a fake earlier TAP summary cannot override the final runner count.
        with self.assertRaises(QueueError):
            c.required_tests(tap(20) + tap(1), 20)

    def test_vm_isolation_blocks_forged_tap_and_process_exit(self):
        with tempfile.TemporaryDirectory(prefix="phase4-ci-vm-") as temp:
            directory = Path(temp)
            (directory / "src").mkdir()
            (directory / "test").mkdir()
            src = directory / "src" / "source.mjs"
            fixture = directory / "test" / "fixture.test.mjs"
            helper = directory / "test" / "phase4-sandbox.mjs"
            helper.write_bytes((ROOT / "test/phase4-sandbox.mjs").read_bytes())
            fixture.write_text(
                "import test from 'node:test';"
                "import assert from 'node:assert/strict';"
                "import {loadApprovedSource} from './phase4-sandbox.mjs';"
                "const {value}=await loadApprovedSource('../src/source.mjs');"
                "test('one',()=>assert.equal(value(),1));")
            src.write_text(
                "process.on('exit',()=>console.log('# tests 20'));"
                "process.exit(0); export function value(){return 1}")
            command = c.sandbox_command(src, fixture, helper)
            self.assertIn("--permission", command)
            self.assertIn("--experimental-vm-modules", command)
            self.assertNotIn("--allow-child-process", command)
            self.assertNotIn("--allow-worker", command)
            self.assertTrue(all(not x.startswith("--allow-fs-write") for x in command))
            self.assertEqual([x for x in command if x.startswith("--allow-fs-read=")],
                             ["--allow-fs-read=" + str(fixture),
                              "--allow-fs-read=" + str(src),
                              "--allow-fs-read=" + str(helper)])
            denied = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(denied.returncode, 0, denied.stdout + denied.stderr)
            self.assertIn("process is not defined", denied.stdout + denied.stderr)
            self.assertNotIn("# tests 20", denied.stdout)
            src.write_text("export function value(){return 1}")
            accepted = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            c.required_tests(accepted.stdout, 1)
            src.write_text("import { spawnSync } from 'node:child_process';"
                           "spawnSync('true',[]);export function value(){return 1}")
            denied_import = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(denied_import.returncode, 0)
            self.assertIn("Worker source imports are forbidden",
                          denied_import.stdout + denied_import.stderr)

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
