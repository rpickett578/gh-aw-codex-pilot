"""Observed overlay/provenance regressions and one-use recovery. No AI or network."""
import copy
from contextlib import contextmanager
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
import urllib.error
import zipfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "test/fixtures/phase2-observed.json").read_text())


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load("policy", "scripts/phase2.py")
g = load("guard", "scripts/workspace_guard.py")


def command(root, *args):
    return subprocess.check_output(args, cwd=root, stderr=subprocess.PIPE)


@contextmanager
def observed_workspace():
    with tempfile.TemporaryDirectory(prefix="phase2-guard-test-", dir=ROOT.parent) as directory:
        require_parent = Path(directory).resolve().parent == ROOT.parent.resolve()
        assert require_parent  # cleanup stays in this explicitly created control directory
        root = Path(directory) / "workspace"
        root.mkdir()
        archive = command(ROOT, "git", "archive", FIXTURE["bootstrap_sha"])
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            package.extractall(root, filter="data")
        (root / "src/slugify.mjs").write_text(FIXTURE["reviewed_source"]["text"], encoding="utf-8", newline="\n")
        assert command(root, "git", "hash-object", "src/slugify.mjs").decode().strip() == FIXTURE["reviewed_source"]["blob"]
        command(root, "git", "init", "--quiet")
        command(root, "git", "add", ".")
        command(root, "git", "-c", "user.name=Local regression", "-c", "user.email=validation@example.invalid",
                "commit", "--quiet", "-m", "Exact observed synthetic source tree control")
        overlay = command(ROOT, "git", "archive", FIXTURE["executed_sha"], ".github", "AGENTS.md")
        with tarfile.open(fileobj=io.BytesIO(overlay)) as package:
            package.extractall(root, filter="data")
        yield root, Path(directory) / "host-temp"


class WorkspaceTests(unittest.TestCase):
    def test_actual_overlay_reproduces_old_failure_but_unchanged_snapshot_passes(self):
        with observed_workspace() as (root, _):
            old = subprocess.run(["git", "diff", "--exit-code"], cwd=root, capture_output=True)
            self.assertEqual(old.returncode, 1)
            changed = command(root, "git", "diff", "--name-only").decode().splitlines()
            self.assertEqual(changed, [".github/workflows/ci.yml", "AGENTS.md"])
            status = command(root, "git", "status", "--short").decode()
            self.assertIn("?? .github/workflows/phase2-review.lock.yml", status)
            before = g.snapshot(root)
            g.compare(before, g.snapshot(root), "review")
            self.assertIn(".github/workflows/phase2-review.lock.yml", before["entries"])
            print("OBSERVED REGRESSION: old git diff fails; full unchanged restored-tree snapshot passes")

    def test_review_modification_addition_deletion_and_ignored_files_fail(self):
        with observed_workspace() as (root, _):
            baseline = g.snapshot(root)
            for name in ["AGENTS.md", ".github/workflows/ci.yml", ".github/workflows/phase2-review.lock.yml",
                         "src/slugify.mjs", "test/slugify.test.mjs"]:
                with self.subTest(path=name):
                    path = root / name
                    old = path.read_bytes()
                    path.write_bytes(old + b"\nunauthorized\n")
                    with self.assertRaises(ValueError): g.compare(baseline, g.snapshot(root), "review")
                    path.write_bytes(old)
            path = root / "AGENTS.md"
            old = path.read_bytes(); path.unlink()
            with self.assertRaises(ValueError): g.compare(baseline, g.snapshot(root), "review")
            path.write_bytes(old)
            path = root / ".github/new-file"
            path.write_text("addition")
            with self.assertRaises(ValueError): g.compare(baseline, g.snapshot(root), "review")
            path.unlink()
            # Neither Git ignore rules nor tracked-file filters can hide an addition.
            (root / ".gitignore").write_text("ignored.tmp\n")
            baseline = g.snapshot(root)
            (root / "ignored.tmp").write_text("must be detected")
            with self.assertRaises(ValueError): g.compare(baseline, g.snapshot(root), "review")

    @unittest.skipIf(os.name == "nt", "POSIX executable-bit semantics run in hosted Linux CI")
    def test_mode_change_and_symlink_replacement_fail(self):
        with observed_workspace() as (root, _):
            baseline = g.snapshot(root)
            path = root / "AGENTS.md"
            mode = stat.S_IMODE(path.stat().st_mode)
            path.chmod(mode | stat.S_IXUSR)
            with self.assertRaises(ValueError): g.compare(baseline, g.snapshot(root), "review")
            path.chmod(mode)
            original = path.read_bytes(); path.unlink(); path.symlink_to("TASK.md")
            with self.assertRaises(ValueError): g.compare(baseline, g.snapshot(root), "review")

    def test_correction_scope_allows_only_slug_source_without_ignoring_overlays(self):
        with observed_workspace() as (root, _):
            baseline = g.snapshot(root)
            (root / "src/slugify.mjs").write_text(FIXTURE["reviewed_source"]["text"] + "\n// correction control\n")
            g.compare(baseline, g.snapshot(root), "repair")
            result = subprocess.run(["node", "--permission", "--allow-fs-read="+str(root),
                "--test-isolation=none", "--test", "test/slugify.test.mjs"], cwd=root,
                env={k:os.environ[k] for k in ["PATH","SystemRoot"] if k in os.environ}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("pass 19", result.stdout)
            (root / "AGENTS.md").write_text("tampered overlay")
            with self.assertRaises(ValueError): g.compare(baseline, g.snapshot(root), "repair")

    def test_next_scope_rejects_wrong_file_and_deletion(self):
        with observed_workspace() as (root, _):
            # Next checkout is reviewed main, with its independent source stub.
            (root / "src/reverse-ascii.mjs").write_bytes(command(ROOT, "git", "show", FIXTURE["executed_sha"] + ":src/reverse-ascii.mjs"))
            baseline = g.snapshot(root)
            source = root / "src/reverse-ascii.mjs"
            source.write_text("export function reverseAscii(x) { return x; }\n")
            with self.assertRaises(ValueError): g.compare(baseline, g.snapshot(root), "next", root)
            source.unlink()
            with self.assertRaises(ValueError): g.compare(baseline, g.snapshot(root), "next", root)

    def test_host_only_baseline_capture_check_context_and_no_overwrite(self):
        with observed_workspace() as (root, temporary):
            temporary.mkdir()
            env = dict(os.environ, RUNNER_TEMP=str(temporary), GITHUB_RUN_ID="101", GITHUB_WORKFLOW_SHA="1"*40)
            cmd = [sys.executable, str(ROOT / "scripts/workspace_guard.py")]
            self.assertEqual(subprocess.run(cmd+["capture", "review"], cwd=root, env=env, capture_output=True).returncode, 0)
            baseline = temporary / "phase2-workspace-guard/baseline.json"
            self.assertFalse(baseline.is_relative_to(root))
            self.assertEqual(subprocess.run(cmd+["capture", "review"], cwd=root, env=env, capture_output=True).returncode, 1)
            self.assertEqual(subprocess.run(cmd+["check", "review"], cwd=root, env=env, capture_output=True).returncode, 0)
            env["GITHUB_RUN_ID"] = "102"
            self.assertEqual(subprocess.run(cmd+["check", "review"], cwd=root, env=env, capture_output=True).returncode, 1)

    def test_missing_and_workspace_baseline_rejected(self):
        with observed_workspace() as (root, temporary):
            env = dict(os.environ, RUNNER_TEMP=str(root), GITHUB_RUN_ID="101", GITHUB_WORKFLOW_SHA="1"*40)
            cmd = [sys.executable, str(ROOT / "scripts/workspace_guard.py")]
            self.assertEqual(subprocess.run(cmd+["capture", "review"], cwd=root, env=env, capture_output=True).returncode, 1)
            temporary.mkdir(); env["RUNNER_TEMP"] = str(temporary)
            self.assertEqual(subprocess.run(cmd+["check", "review"], cwd=root, env=env, capture_output=True).returncode, 1)


class EvidenceTests(unittest.TestCase):
    def test_actual_bot_review_and_native_publication_are_authentic(self):
        p.validate_review(FIXTURE["review"], str(p.FAILED_RUN))
        p.validate_publication(FIXTURE["review"], FIXTURE["run"], [FIXTURE["publisher"]], FIXTURE["publication_items"])

    def test_wrong_author_bot_id_type_commit_event_run_and_marker_rejected(self):
        for field in ["login", "id", "type", "commit", "event", "run", "marker", "url"]:
            with self.subTest(field=field):
                row = copy.deepcopy(FIXTURE["review"])
                if field in ["login", "id", "type"]: row["user"][field] = {"login":"rpickett578","id":1,"type":"User"}[field]
                if field == "commit": row["commit_id"] = "0"*40
                if field == "event": row["state"] = "APPROVED"
                if field == "run": row["body"] = row["body"].replace(str(p.FAILED_RUN), "999")
                if field == "marker": row["body"] = row["body"].split("<!--")[0]
                if field == "url": row["html_url"] = row["html_url"].replace("/pull/2", "/pull/3")
                with self.assertRaises(ValueError): p.validate_review(row, str(p.FAILED_RUN))

    def test_manifest_and_successful_publisher_required(self):
        for kind in ["missing", "wrong_id", "wrong_event", "failed_job", "wrong_run", "timestamp"]:
            with self.subTest(kind=kind):
                rows = copy.deepcopy(FIXTURE["publication_items"]); job = copy.deepcopy(FIXTURE["publisher"])
                if kind == "missing": rows = []
                if kind == "wrong_id": rows[0]["id"] += 1
                if kind == "wrong_event": rows[0]["metadata"]["review_event"] = "APPROVE"
                if kind == "failed_job": job["conclusion"] = "failure"
                if kind == "wrong_run": job["run_id"] += 1
                if kind == "timestamp": job["started_at"] = "2099-01-01T00:00:00Z"
                with self.assertRaises(ValueError): p.validate_publication(FIXTURE["review"], FIXTURE["run"], [job], rows)

    def test_native_artifact_download_does_not_forward_bearer_token(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,"w") as archive:
            archive.writestr("safe-output-items.jsonl",json.dumps(FIXTURE["publication_items"][0])+"\n")
        location="https://productionresultssa17.blob.core.windows.net/synthetic-artifact"
        redirect=urllib.error.HTTPError("https://api.github.com",302,"redirect",{"Location":location},None)
        inventory={"total_count":1,"artifacts":[{"id":1,"name":"example-safe-outputs-items","expired":False,"size_in_bytes":944}]}
        with patch.dict(os.environ,{"GH_TOKEN":"non-secret-unit-test-token"}), patch.object(p,"api",return_value=inventory), \
             patch.object(p.urllib.request,"build_opener") as opener, patch.object(p.urllib.request,"urlopen",return_value=io.BytesIO(data.getvalue())) as download:
            opener.return_value.open.side_effect=redirect
            self.assertEqual(p.publication_items(101),FIXTURE["publication_items"])
            request=download.call_args.args[0]
            self.assertIsNone(request.get_header("Authorization"))
            self.assertEqual(request.full_url,location)

    def test_untrusted_artifact_host_rejected_before_download(self):
        inventory={"total_count":1,"artifacts":[{"id":1,"name":"example-safe-outputs-items","expired":False,"size_in_bytes":944}]}
        redirect=urllib.error.HTTPError("https://api.github.com",302,"redirect",{"Location":"https://example.invalid/artifact"},None)
        with patch.dict(os.environ,{"GH_TOKEN":"non-secret-unit-test-token"}), patch.object(p,"api",return_value=inventory), \
             patch.object(p.urllib.request,"build_opener") as opener, patch.object(p.urllib.request,"urlopen") as download:
            opener.return_value.open.side_effect=redirect
            with self.assertRaises(ValueError): p.publication_items(101)
            download.assert_not_called()

    def test_old_authentic_review_cannot_supply_new_run(self):
        with self.assertRaises(ValueError): p.validate_review(FIXTURE["review"], "101")

    def test_pending_publication_metadata_waits_without_resubmission(self):
        expected=(FIXTURE["review"],{"verdict":"clean","findings":[]})
        with patch.object(p,"_read_review_evidence",side_effect=[ValueError("publisher metadata not yet complete"),expected]) as read, \
             patch.object(p.time,"sleep") as sleep:
            self.assertEqual(p.review_evidence(wait=True),expected)
            self.assertEqual(read.call_count,2)
            sleep.assert_called_once_with(10)

    def test_failed_or_exhausted_publication_metadata_fails_closed(self):
        with patch.object(p,"_read_review_evidence",side_effect=ValueError("publisher failed")), patch.object(p.time,"sleep") as sleep:
            with self.assertRaises(ValueError): p.review_evidence(wait=True)
            sleep.assert_not_called()
        with patch.object(p,"_read_review_evidence",side_effect=ValueError("publisher metadata not yet complete")) as read, patch.object(p.time,"sleep") as sleep:
            with self.assertRaises(ValueError): p.review_evidence(wait=True)
            self.assertEqual(read.call_count,13)
            self.assertEqual(sleep.call_count,12)

    def test_forged_current_run_review_is_not_treated_as_delay(self):
        row=copy.deepcopy(FIXTURE["review"]); row["user"]["login"]="rpickett578"
        with patch.dict(os.environ,{"GITHUB_RUN_ID":str(p.FAILED_RUN)}), patch.object(p,"api",return_value=[row]) as read, patch.object(p.time,"sleep") as sleep:
            with self.assertRaises(ValueError): p.review_evidence(wait=True)
            self.assertEqual(read.call_count,1)
            sleep.assert_not_called()

    def test_native_repair_output_or_exact_empty_child_only(self):
        repair = "1"*40; child = "2"*40
        p.validate_repair_head(repair, repair)
        parent = {"parents":[{"sha":repair}], "commit":{"tree":{"sha":"same"}}}
        p.validate_repair_head(child, repair, parent, {"commit":{"tree":{"sha":"same"}}})
        with self.assertRaises(ValueError): p.validate_repair_head(child, repair, parent, {"commit":{"tree":{"sha":"different"}}})
        parent["parents"] = [{"sha":"3"*40}]
        with self.assertRaises(ValueError): p.validate_repair_head(child, repair, parent, {"commit":{"tree":{"sha":"same"}}})

    def test_clean_review_admits_route_continue_next_and_fixed_publication_locally(self):
        # Exercise the downstream admission paths with mocked GitHub evidence, not a hosted AI claim.
        review=copy.deepcopy(FIXTURE["review"]); review["body"]=review["body"].replace(str(p.FAILED_RUN),"101")
        run=dict(FIXTURE["run"],id=101,head_sha="1"*40,display_title=p.RECOVERY_KEY)
        publisher=dict(FIXTURE["publisher"],run_id=101,head_sha="1"*40)
        pr={"number":2,"state":"open","draft":True,
            "head":{"sha":p.HEAD,"ref":p.BRANCH,"repo":{"full_name":p.REPO}},
            "base":{"ref":"main","repo":{"full_name":p.REPO}}}
        responses={"/pulls/2":pr,"/pulls/2/reviews?per_page=100":[review],"/actions/runs/101":run,
            "/actions/runs/101/jobs?per_page=100":{"total_count":1,"jobs":[publisher]},
            "/git/ref/heads/"+p.NEXT_BRANCH:None}
        with tempfile.TemporaryDirectory(prefix="phase2-route-",dir=ROOT.parent) as temporary:
            output=Path(temporary)/"outputs"; agent=Path(temporary)/"agent.json"
            agent.write_text(json.dumps({"items":[{"type":"create_pull_request","branch":"phase2-reverse-ascii-v1"}]}))
            env={"GITHUB_REPOSITORY":p.REPO,"GITHUB_RUN_ATTEMPT":"1","GITHUB_WORKFLOW_SHA":"1"*40,
                "GITHUB_RUN_ID":"101","PHASE2_EXECUTION_SHA":"1"*40,"PHASE2_RECOVERY_KEY":p.RECOVERY_KEY,
                "GITHUB_OUTPUT":str(output),"REVIEW_ID":str(review["id"]),"EXPECTED_HEAD":p.HEAD,"GH_AW_AGENT_OUTPUT":str(agent)}
            with patch.dict(os.environ,env,clear=True), patch.object(p,"api",side_effect=lambda path,**kwargs:copy.deepcopy(responses[path])), \
                 patch.object(p,"publication_items",return_value=FIXTURE["publication_items"]), patch.object(p,"actual_ci") as ci:
                for stage in ["route","continue","next","publish-next"]:
                    with patch.object(sys,"argv",["phase2.py",stage]): p.entry()
                self.assertIn("repair=false",output.read_text())
                self.assertIn("head_sha="+p.HEAD,output.read_text())
                self.assertEqual(ci.call_count,3)
                agent.write_text(json.dumps({"items":[{"type":"create_pull_request","branch":"unapproved-task"}]}))
                with patch.object(sys,"argv",["phase2.py","publish-next"]):
                    with self.assertRaises(ValueError): p.entry()


class RecoveryTests(unittest.TestCase):
    def rows(self, new_id=101):
        old = dict(FIXTURE["run"])
        new = {"id":new_id,"display_title":p.RECOVERY_KEY,"head_sha":"1"*40,"run_attempt":1}
        consumed = {"id":p.CONSUMED_RECOVERY_RUN,"display_title":p.RECOVERY_V1_KEY,"head_sha":p.CONSUMED_RECOVERY_SHA,
                    "status":"completed","conclusion":"success","run_attempt":1}
        v2 = {"id":p.CONSUMED_V2_RUN,"display_title":p.RECOVERY_V2_KEY,"head_sha":p.CONSUMED_V2_SHA,
              "status":"completed","conclusion":"failure","run_attempt":1}
        return [old,new,consumed,v2]

    def test_original_key_remains_consumed(self):
        with self.assertRaises(ValueError): p.one_attempt(self.rows(), "101")

    def test_exact_failed_run_permits_one_separately_gated_recovery(self):
        with patch.dict(os.environ, {"GITHUB_WORKFLOW_SHA":"1"*40}):
            p.recovery_admission(self.rows(), "101")
            rows = self.rows(); rows.append(dict(rows[1], id=102))
            with self.assertRaises(ValueError): p.recovery_admission(rows, "102")

    def test_failed_recovery_also_consumes_replacement_key(self):
        rows = self.rows(); rows[1].update(status="completed",conclusion="failure")
        rows.append(dict(rows[1],id=102))
        with patch.dict(os.environ, {"GITHUB_WORKFLOW_SHA":"1"*40}):
            with self.assertRaises(ValueError): p.recovery_admission(rows, "102")

    def test_wrong_old_failure_unknown_attempt_and_same_run_replay_rejected(self):
        with patch.dict(os.environ, {"GITHUB_WORKFLOW_SHA":"1"*40}):
            rows=self.rows(); rows[0]["conclusion"]="success"
            with self.assertRaises(ValueError): p.recovery_admission(rows,"101")
            rows=self.rows(); rows.append({"id":999,"display_title":"unknown"})
            with self.assertRaises(ValueError): p.recovery_admission(rows,"101")
            with self.assertRaises(ValueError): p.recovery_admission([FIXTURE["run"]], str(p.FAILED_RUN))

    def test_missing_gate_wrong_key_and_second_attempt_stop_before_api(self):
        common={"GITHUB_REPOSITORY":p.REPO,"GITHUB_WORKFLOW_SHA":"1"*40,"PHASE2_EXECUTION_SHA":"1"*40,
                "GITHUB_RUN_ATTEMPT":"1","PHASE2_RECOVERY_KEY":p.RECOVERY_KEY}
        for changes in [{"PHASE2_EXECUTION_SHA":""},{"PHASE2_RECOVERY_KEY":""},
                        {"PHASE2_RECOVERY_KEY":p.KEY+"-unknown-recovery"},{"GITHUB_RUN_ATTEMPT":"2"}]:
            with patch.dict(os.environ, dict(common, **changes), clear=True), patch.object(p,"api") as request:
                with self.assertRaises(ValueError): p.entry()
                request.assert_not_called()


class CompiledBoundaryTests(unittest.TestCase):
    def test_observed_sandbox_has_no_baseline_mount_or_host_access(self):
        sandbox=FIXTURE["sandbox"]
        self.assertFalse(sandbox["enableHostAccess"])
        baseline=PurePosixPath('/home/runner/work/_temp/phase2-workspace-guard')
        for mount in sandbox["volumeMounts"]:
            source,destination,mode=mount.split(":")
            self.assertFalse(baseline.is_relative_to(PurePosixPath(source)))
            self.assertFalse(baseline.is_relative_to(PurePosixPath(destination)))

    def test_guard_runs_after_restoration_and_before_engine_and_not_mounted(self):
        for stage in ["review","repair","next"]:
            text=(ROOT/f".github/workflows/phase2-{stage}.lock.yml").read_text()
            self.assertLess(text.index("Restore agent config folders from base branch"), text.index('capture "$PHASE2_STAGE"'))
            self.assertLess(text.index('capture "$PHASE2_STAGE"'), text.index('awf --config'))
            self.assertLess(text.index('awf --config'), text.index('check "$PHASE2_STAGE"'))
            for line in text.splitlines():
                if 'awf --config' in line:
                    self.assertNotIn('--mount "${RUNNER_TEMP}:',line)
                    self.assertNotIn('phase2-workspace-guard',line)
            self.assertIn('AGENT_JOB_RESULT: ${{ needs.agent.result }}', text)
            self.assertLess(text.index('test "$AGENT_JOB_RESULT" = success'), text.index('name: Process Safe Outputs'))


if __name__ == "__main__":
    unittest.main()
