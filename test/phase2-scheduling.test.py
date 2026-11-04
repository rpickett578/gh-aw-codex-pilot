"""Acceptance and consumed-key controls. Scheduling itself is proved by real PR CI jobs."""
import copy
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("policy", ROOT / "scripts/phase2.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


class AcceptanceTests(unittest.TestCase):
    def results(self):
        return {"admit":"success","review":"success","route":"success","repair":"skipped",
                "continue":"success","next":"success"}

    def test_clean_path_requires_mandatory_next(self):
        p.validate_completion(self.results(),"false","7",f"https://github.com/{p.REPO}/pull/7","false")
        for job in ["admit","review","route","continue","next"]:
            for status in ["skipped","failure","cancelled",""]:
                with self.subTest(job=job,status=status):
                    rows=dict(self.results(),**{job:status})
                    with self.assertRaises(ValueError): p.validate_completion(rows,"false","7",f"https://github.com/{p.REPO}/pull/7","false")

    def test_missing_pr_outputs_cancel_and_wrong_repair_fail(self):
        for number,url in [("",""),("0",f"https://github.com/{p.REPO}/pull/0"),("7","https://example.invalid/pull/7")]:
            with self.assertRaises(ValueError): p.validate_completion(self.results(),"false",number,url,"false")
        for required,cancelled in [("true","false"),("false","true"),("","false")]:
            with self.assertRaises(ValueError): p.validate_completion(self.results(),required,"7",f"https://github.com/{p.REPO}/pull/7",cancelled)
        p.validate_completion(dict(self.results(),repair="success"),"true","7",f"https://github.com/{p.REPO}/pull/7","false")

    def fixture(self):
        url=f"https://github.com/{p.REPO}/pull/7"
        pr={"number":7,"html_url":url,"state":"open","draft":True,"merged":False,
            "head":{"ref":p.NEXT_BRANCH,"sha":"1"*40,"repo":{"full_name":p.REPO}},
            "base":{"ref":"main","repo":{"full_name":p.REPO}}}
        item={"type":"create_pull_request","status":"success","repo":p.REPO,"number":7,"url":url}
        return pr,[{"filename":p.NEXT_SOURCE}],[item]

    def test_actual_pr_scope_and_native_publication_required(self):
        pr,files,items=self.fixture()
        p.accept_next_pr("7",pr["html_url"],pr,files,items)
        for kind in ["closed","not-draft","merged","fork","branch","files","no-publication","wrong-publication"]:
            with self.subTest(kind=kind):
                row=copy.deepcopy(pr); paths=copy.deepcopy(files); evidence=copy.deepcopy(items)
                if kind=="closed": row["state"]="closed"
                if kind=="not-draft": row["draft"]=False
                if kind=="merged": row["merged"]=True
                if kind=="fork": row["head"]["repo"]["full_name"]="unrelated/repo"
                if kind=="branch": row["head"]["ref"]="codex/unapproved"
                if kind=="files": paths.append({"filename":"test/reverse-ascii.test.mjs"})
                if kind=="no-publication": evidence=[]
                if kind=="wrong-publication": evidence[0]["number"]=99
                with self.assertRaises(ValueError): p.accept_next_pr("7",pr["html_url"],row,paths,evidence)

    def test_real_ci_is_required_after_native_pr_verification(self):
        pr,files,items=self.fixture()
        env={"GITHUB_REPOSITORY":p.REPO,"GITHUB_RUN_ATTEMPT":"1","GITHUB_RUN_ID":"101",
            "GITHUB_WORKFLOW_SHA":"1"*40,"PHASE2_EXECUTION_SHA":"1"*40,"PHASE2_RECOVERY_KEY":p.RECOVERY_KEY,
            "REPAIR_REQUIRED":"false","RUN_CANCELLED":"false","NEXT_PR_NUMBER":"7","NEXT_PR_URL":pr["html_url"],"EXPECTED_HEAD":p.HEAD}
        env.update({job.upper()+"_RESULT":status for job,status in self.results().items()})
        with patch.dict(os.environ,env,clear=True), patch.object(sys,"argv",["phase2.py","accept"]), \
             patch.object(p,"validate_pr"), patch.object(p,"review_evidence"), \
             patch.object(p,"api",side_effect=[{},pr,files]), patch.object(p,"publication_items",return_value=items), \
             patch.object(p,"actual_ci",side_effect=ValueError("required CI pending")) as ci:
            with self.assertRaises(ValueError): p.entry()
            ci.assert_called_once_with(pr["head"]["sha"],wait=True)


class ConsumedKeyTests(unittest.TestCase):
    def history(self):
        return [{"id":p.FAILED_RUN,"display_title":p.KEY,"head_sha":p.FAILED_SHA,"status":"completed","conclusion":"failure","run_attempt":1},
                {"id":p.CONSUMED_RECOVERY_RUN,"display_title":p.RECOVERY_V1_KEY,"head_sha":p.CONSUMED_RECOVERY_SHA,"status":"completed","conclusion":"success","run_attempt":1},
                {"id":101,"display_title":p.RECOVERY_KEY,"head_sha":"1"*40,"run_attempt":1}]

    def test_both_prior_keys_remain_consumed(self):
        rows=self.history()
        for key in [p.KEY,p.RECOVERY_V1_KEY]:
            with self.assertRaises(ValueError): p.one_attempt(rows,"101",key)

    def test_only_one_explicit_v2_with_exact_two_prior_runs(self):
        with patch.dict(os.environ,{"GITHUB_WORKFLOW_SHA":"1"*40}):
            p.recovery_admission(self.history(),"101")
            rows=self.history(); rows.append(dict(rows[-1],id=102))
            with self.assertRaises(ValueError): p.recovery_admission(rows,"102")
            rows=self.history(); rows[1]["run_attempt"]=2
            with self.assertRaises(ValueError): p.recovery_admission(rows,"101")


class WiringTests(unittest.TestCase):
    def test_native_fixture_matches_corrected_caller_condition(self):
        root=(ROOT/".github/workflows/phase2-chain.yml").read_text()
        ci=(ROOT/".github/workflows/ci.yml").read_text()
        condition="if: ${{ !cancelled() && needs.route.result == 'success' && needs.continue.result == 'success' }}"
        self.assertIn(condition,root)
        self.assertIn(condition.replace("needs.route","needs.schedule_route").replace("needs.continue","needs.schedule_continue"),ci)
        self.assertIn("uses: ./.github/workflows/phase2-scheduling-worker.yml",ci)
        self.assertIn("needs: [schedule_route, schedule_repair]",ci)
        fixture=(ROOT/".github/workflows/phase2-scheduling-worker.yml").read_text()
        for text in [fixture,ci.split("  verify:")[0]]:
            self.assertNotIn("secrets.",text)
            self.assertNotIn("secrets: inherit",text)
            self.assertNotIn("GH_TOKEN",text)
        self.assertIn("  acceptance:\n    needs: [admit, review, route, repair, continue, next]\n    if: always()",root)
        self.assertIn("NEXT_PR_NUMBER: ${{ needs.next.outputs.created_pr_number }}",root)
        self.assertIn("name: synthetic-tests\n    needs: scheduling_proof\n    if: always()",ci)


if __name__ == "__main__":
    unittest.main()
