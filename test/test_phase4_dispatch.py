"""No-network regression tests for the Phase4 dispatch/ledger planner."""
import base64
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import phase4_dispatch as dp

MAIN = "a" * 40
HEAD = "b" * 40


def manifest(budget=60):
    return {"version": 1, "repository": dp.REPO, "tasks": [
        {"id": "next-safe-v1", "issue": 21,
         "allowed_files": ["src/next-safe-v1.mjs"],
         "max_ai_credits": budget}]}


def snapshot():
    return {"pulls": [
        {"number": 77, "head": {"sha": HEAD}}],
        "issues": {"21": {"number": 21, "state": "open"}}}


def selected(stage="READY_CODING"):
    return {"action": stage, "index": 0, "task": "next-safe-v1",
            "issue": 21, "max_ai_credits": 60,
            "allowed_files": ["src/next-safe-v1.mjs"],
            "pr": 77 if stage == "READY_REVIEW" else None}


def claim(stage="READY_CODING"):
    return {"task": "next-safe-v1", "stage": stage,
            "issue": 21, "source": "src/next-safe-v1.mjs",
            "pr": 77 if stage == "READY_REVIEW" else None,
            "head": HEAD if stage == "READY_REVIEW" else "",
            "cost": dp.STAGE_CREDITS[stage], "run_id": 12,
            "install_sha": MAIN}


class DispatchTests(unittest.TestCase):
    def plan(self, stage, ledger=None, budget=60):
        with patch.object(dp, "decide", return_value=selected(stage)):
            return dp.decide_claim(manifest(budget), snapshot(),
                                   ledger or dp.initial_ledger(), 15, MAIN)

    def test_empty_queue_never_launches(self):
        with patch.object(dp, "decide", return_value={"action": "QUEUE_EMPTY"}):
            r = dp.decide_claim(manifest(), snapshot(), dp.initial_ledger(), 15, MAIN)
        self.assertEqual(r, {"decision": "NO_LAUNCH", "reason": "QUEUE_EMPTY"})

    def test_wait_ci_and_repair_do_not_launch(self):
        for stage in ("WAIT_CI", "READY_REPAIR"):
            self.assertEqual(self.plan(stage)["decision"], "NO_LAUNCH")

    def test_first_coder_reserves_only_33(self):
        r = self.plan("READY_CODING")
        self.assertEqual(r["decision"], "RESERVE")
        self.assertEqual(r["claim"]["source"], "src/next-safe-v1.mjs")
        self.assertEqual(r["claim"]["cost"], 33)
        self.assertEqual(r["remaining_credits"], 27)

    def test_duplicate_claim_never_reruns_paid_stage(self):
        ledger = dp.initial_ledger()
        ledger["claims"].append(claim())
        r = self.plan("READY_CODING", ledger)
        self.assertEqual(r["decision"], "HELD")

    def test_reviewer_requires_prior_coder_claim(self):
        with self.assertRaises(dp.QueueError):
            self.plan("READY_REVIEW")

    def test_reviewer_reserves_other_20_only(self):
        ledger = dp.initial_ledger()
        ledger["claims"].append(claim())
        r = self.plan("READY_REVIEW", ledger)
        self.assertEqual(r["claim"]["head"], HEAD)
        self.assertEqual(r["claim"]["pr"], 77)
        self.assertEqual(r["claim"]["cost"], 20)
        self.assertEqual(r["remaining_credits"], 7)

    def test_altered_head_is_rejected(self):
        ledger = dp.initial_ledger()
        ledger["claims"].append(claim())
        with patch.object(dp, "decide", return_value=selected("READY_REVIEW")):
            with self.assertRaises(dp.QueueError):
                dp.decide_claim(manifest(), {"pulls": []}, ledger, 15, MAIN)

    def test_budget_under_combined_envelope_fails(self):
        with self.assertRaises(dp.QueueError):
            self.plan("READY_CODING", budget=52)

    def test_ledger_wrong_scope_fails_closed(self):
        ledger = dp.initial_ledger()
        forged = claim()
        forged["source"] = "src/other-task.mjs"
        ledger["claims"].append(forged)
        with self.assertRaises(dp.QueueError):
            self.plan("READY_REVIEW", ledger)

    def test_duplicate_ledger_stage_is_rejected(self):
        ledger = dp.initial_ledger()
        ledger["claims"] = [claim(), claim()]
        with self.assertRaises(dp.QueueError):
            dp.validate_ledger(ledger)

    def test_bad_cost_or_install_sha_is_rejected(self):
        ledger = dp.initial_ledger()
        forged = claim()
        forged["cost"] = 60
        ledger["claims"].append(forged)
        with self.assertRaises(dp.QueueError):
            dp.validate_ledger(ledger)
        forged["cost"] = 33
        forged["install_sha"] = "bad"
        with self.assertRaises(dp.QueueError):
            dp.validate_ledger(ledger)

    def test_ledger_read_uses_pinned_branch(self):
        data = dp.initial_ledger()
        encoded = base64.b64encode(json.dumps(data).encode()).decode()
        with patch.object(dp, "get", return_value={
                "content": encoded, "encoding": "base64", "sha": MAIN}) as mocked:
            parsed, sha = dp.read_ledger()
        self.assertEqual(parsed, data)
        self.assertEqual(sha, MAIN)
        self.assertIn("phase4-dispatch-ledger", mocked.call_args.args[0])

    def test_failed_optimistic_write_cannot_authorize_worker(self):
        err = urllib.error.HTTPError("mock", 409, "conflict", {}, None)
        with patch.dict("os.environ", {"GH_TOKEN": "not-a-real-token"}):
            with patch.object(dp.urllib.request, "urlopen", side_effect=err):
                with self.assertRaises(dp.QueueError):
                    dp.write_claim(dp.initial_ledger(), MAIN)


if __name__ == "__main__":
    unittest.main()
