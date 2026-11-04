"""Deterministic gate controls. No GitHub calls, AI, or remote writes."""
import copy
import importlib.util
import json
import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("policy", ROOT / "scripts/phase2.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def review(findings=None):
    data = {"run_id": "101", "head": p.HEAD, "verdict": "findings" if findings else "clean", "findings": findings or []}
    original = json.loads((ROOT / "test/fixtures/phase2-observed.json").read_text())["review"]
    original["body"] = ("```phase2-review\n" + json.dumps(data) + "\n```\n"
        + f'<!-- id: 101, workflow_id: phase2-review, run: https://github.com/{p.REPO}/actions/runs/101 -->\n'
        + '[gh-aw-workflow-call-id]: # "rpickett578%2Fgh-aw-codex-pilot%2Fphase2-review"')
    return original


class GateTests(unittest.TestCase):
    def test_clean_review_is_valid(self):
        self.assertEqual(p.validate_review(review(), "101")["verdict"], "clean")

    def test_comment_is_not_an_approval(self):
        for state in ["APPROVED", "CHANGES_REQUESTED", "PENDING"]:
            row = review(); row["state"] = state
            with self.assertRaises(ValueError): p.validate_review(row, "101")

    def test_wrong_review_head_rejected(self):
        row = review(); row["commit_id"] = "0" * 40
        with self.assertRaises(ValueError): p.validate_review(row, "101")

    def test_other_run_cannot_supply_review(self):
        with self.assertRaises(ValueError): p.validate_review(review(), "102")

    def test_unknown_disposition_rejected(self):
        row = review(); row["body"] = row["body"].replace('"clean"', '"APPROVE"')
        with self.assertRaises(ValueError): p.validate_review(row, "101")

    def test_invented_expected_behavior_rejected(self):
        finding = {"input": "A B", "expected": {"value": "ab"}, "line": 4, "reason": "wrong expectation"}
        with self.assertRaises(ValueError): p.validate_review(review([finding]), "101")

    def test_separate_seed_reproduces_and_correct_control_resolves(self):
        finding = {"input": "A   B", "expected": {"value": "a-b"}, "line": 3, "reason": "separator run not collapsed"}
        evidence = p.validate_review(review([finding]), "101")
        bad = (ROOT / "fixtures/seeded-defect/slugify.mjs").read_bytes()
        good = b"export function slugify(x) { if(typeof x!=='string')throw new TypeError(); return x.replace(/[^A-Za-z0-9]+/g,'-').toLowerCase().replace(/^-|-$/g,''); }"
        p.validate_findings(evidence, bad)
        p.validate_findings(evidence, good, fixed=True)
        with self.assertRaises(ValueError): p.validate_findings(evidence, good)
        with self.assertRaises(ValueError): p.validate_findings(evidence, bad, fixed=True)

    def test_clean_means_repair_not_applicable(self):
        with self.assertRaises(ValueError): p.validate_findings({"findings": []}, b"")

    def test_duplicate_attempt_rejected_even_after_failure(self):
        with self.assertRaises(ValueError): p.one_attempt([{"id": 100, "display_title": p.KEY}], "101")
        p.one_attempt([{"id": 101, "display_title": p.KEY}], "101")

    def test_ambiguous_or_unbounded_history_rejected(self):
        with self.assertRaises(ValueError): p.one_attempt([{"id": i, "display_title": "other"} for i in range(100)], "101")

    def test_pending_ci_never_means_success(self):
        check = {"name": "synthetic-tests", "head_sha": p.HEAD, "app": {"slug": "github-actions"}, "status": "queued", "conclusion": None}
        run = {"head_sha": p.HEAD, "path": ".github/workflows/ci.yml", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 1}
        with self.assertRaises(ValueError): p.ci_success([check], [run], p.HEAD)
        check.update(status="completed", conclusion="success")
        p.ci_success([check], [run], p.HEAD)
        for field, value in [("head_sha", "0"*40), ("conclusion", "failure")]:
            other = dict(check, **{field: value})
            with self.assertRaises(ValueError): p.ci_success([other], [run], p.HEAD)

    def test_fake_check_and_duplicate_check_rejected(self):
        check = {"name": "synthetic-tests", "head_sha": p.HEAD, "app": {"slug": "fake"}, "status": "completed", "conclusion": "success"}
        with self.assertRaises(ValueError): p.ci_success([check], [], p.HEAD)
        with self.assertRaises(ValueError): p.ci_success([check, check], [], p.HEAD)

    def test_exact_branch_and_repository_required(self):
        pr = {"number": 2, "state": "open", "draft": True, "head": {"sha": p.HEAD, "ref": p.BRANCH, "repo": {"full_name": p.REPO}}, "base": {"ref": "main", "repo": {"full_name": p.REPO}}}
        p.validate_pr(pr, p.HEAD)
        for kind in ["fork", "branch", "sha", "closed"]:
            other = copy.deepcopy(pr)
            if kind == "fork": other["head"]["repo"]["full_name"] = "another/repo"
            if kind == "branch": other["head"]["ref"] = "main"
            if kind == "sha": other["head"]["sha"] = "0" * 40
            if kind == "closed": other["state"] = "closed"
            with self.assertRaises(ValueError): p.validate_pr(other, p.HEAD)

    def test_compiled_review_enforces_comment_only_at_runtime(self):
        text = (ROOT / ".github/workflows/phase2-review.lock.yml").read_text(encoding="utf-8")
        configs = []
        for line in text.splitlines():
            if "GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG: " in line:
                encoded = line.split("GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG: ", 1)[1]
                configs.append(json.loads(json.loads(encoded)))
        self.assertEqual(len(configs), 1)
        c = configs[0]
        self.assertEqual(c["submit_pull_request_review"]["allowed_events"], ["COMMENT"])
        self.assertEqual(c["submit_pull_request_review"]["commit_id"], p.HEAD)
        self.assertEqual(c["submit_pull_request_review"]["target"], "2")
        self.assertEqual(c["create_pull_request_review_comment"]["max"], 3)
        self.assertNotIn("merge_pull_request", c)

    def test_missing_execution_authorization_stops_before_api(self):
        env = {"GITHUB_REPOSITORY": p.REPO, "GITHUB_RUN_ATTEMPT": "1", "GITHUB_WORKFLOW_SHA": "1"*40}
        with patch.dict(os.environ, env, clear=True), patch.object(p, "api") as request, patch.object(sys, "argv", ["phase2.py", "admit"]):
            with self.assertRaises(ValueError): p.entry()
            request.assert_not_called()

    def test_second_attempt_stops_before_api(self):
        env = {"GITHUB_REPOSITORY": p.REPO, "GITHUB_RUN_ATTEMPT": "2", "GITHUB_WORKFLOW_SHA": "1"*40, "PHASE2_EXECUTION_SHA": "1"*40}
        with patch.dict(os.environ, env, clear=True), patch.object(p, "api") as request, patch.object(sys, "argv", ["phase2.py", "admit"]):
            with self.assertRaises(ValueError): p.entry()
            request.assert_not_called()

    def test_failed_or_retried_ci_cannot_admit_next_task(self):
        check = {"name": "synthetic-tests", "head_sha": p.HEAD, "app": {"slug": "github-actions"}, "status": "completed", "conclusion": "success"}
        run = {"head_sha": p.HEAD, "path": ".github/workflows/ci.yml", "event": "pull_request", "status": "completed", "conclusion": "success", "run_attempt": 2}
        with self.assertRaises(ValueError): p.ci_success([check], [run], p.HEAD)
        run.update(run_attempt=1, conclusion="failure")
        with self.assertRaises(ValueError): p.ci_success([check], [run], p.HEAD)


if __name__ == "__main__":
    unittest.main()
