"""Offline checks: only the reviewed PR16 merge can inherit the old approval."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import phase3_gate as gate
import phase3_snapshot as snapshot

NEW_SHA = "b" * 40
PR_HEAD = "c" * 40


def fixtures():
    commit = {"parents": [{"sha": gate.FIRST_INSTALL_SHA}, {"sha": PR_HEAD}]}
    pr = {"merged": True, "state": "closed", "merge_commit_sha": NEW_SHA,
          "head": {"sha": PR_HEAD, "repo": {"full_name": gate.REPO}}}
    state = {"code_review": {"commit_sha": PR_HEAD, "status": "completed",
                             "has_any_findings": False, "has_unresolved_findings": False}}
    comments = [{"user": {"login": "chatgpt-codex-connector[bot]"},
                 "body": "<!-- codex-review-state:v1 " + json.dumps(state) + " -->"}]
    checks = [{"name": name, "head_sha": PR_HEAD,
               "app": {"slug": "github-actions"},
               "status": "completed", "conclusion": "success"}
              for name in ("synthetic-tests", "scheduling_proof")]
    return commit, pr, comments, checks


def inspect(commit, pr, comments, checks, sha=NEW_SHA):
    def fake_api(path, optional=False):
        if path == "/commits/" + sha:
            return commit
        if path == "/pulls/16":
            return pr
        raise AssertionError("unexpected API: " + path)

    def fake_bounded(path, key=None):
        if path == "/issues/16/comments?per_page=100":
            return comments
        if path == "/commits/" + PR_HEAD + "/check-runs?per_page=100":
            return checks
        if path == "/actions/workflows/ci.yml/runs?event=pull_request&head_sha=" + PR_HEAD + "&per_page=100":
            return [{"head_sha": PR_HEAD, "path": ".github/workflows/ci.yml",
                     "event": "pull_request", "run_attempt": 1,
                     "status": "completed", "conclusion": "success"}]
        raise AssertionError("unexpected collection: " + path)

    with patch.object(snapshot, "api", side_effect=fake_api), \
         patch.object(snapshot, "bounded", side_effect=fake_bounded):
        return snapshot.reviewed_resume_install(sha)


class ReviewedResumeTests(unittest.TestCase):
    def test_original_commit_does_not_need_a_pr16_receipt(self):
        with patch.object(snapshot, "api", side_effect=AssertionError("unexpected network")):
            self.assertFalse(snapshot.reviewed_resume_install(gate.FIRST_INSTALL_SHA))

    def test_exact_verified_pr16_merge_can_reuse_original_approval(self):
        self.assertTrue(inspect(*fixtures()))

    def test_future_install_cannot_reuse_this_approval(self):
        commit, pr, comments, checks = fixtures()
        self.assertFalse(inspect(commit, pr, comments, checks, "d" * 40))

    def test_unreviewed_head_or_untrusted_comment_rejected(self):
        commit, pr, comments, checks = fixtures()
        comments[0]["body"] = comments[0]["body"].replace(
            '"has_any_findings": false', '"has_any_findings": true')
        self.assertFalse(inspect(commit, pr, comments, checks))
        commit, pr, comments, checks = fixtures()
        comments[0]["user"]["login"] = "rpickett578"
        self.assertFalse(inspect(commit, pr, comments, checks))

    def test_failed_exact_head_ci_rejected(self):
        commit, pr, comments, checks = fixtures()
        checks[0]["conclusion"] = "failure"
        self.assertFalse(inspect(commit, pr, comments, checks))

    def test_foreign_ci_check_app_rejected(self):
        commit, pr, comments, checks = fixtures()
        checks[0]['app']['slug'] = "third-party"
        self.assertFalse(inspect(commit, pr, comments, checks))

    def test_foreign_check_sha_rejected(self):
        commit, pr, comments, checks = fixtures()
        checks[0]['head_sha'] = "f" * 40
        self.assertFalse(inspect(commit, pr, comments, checks))


if __name__ == "__main__":
    unittest.main()
