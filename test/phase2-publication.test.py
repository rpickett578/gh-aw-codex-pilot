"""Real-Git commit/working-tree controls; native tool transport is tested separately on Linux CI."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("guard", ROOT / "scripts/workspace_guard.py")
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
SOURCE = "src/reverse-ascii.mjs"
PATCH = ROOT / "evidence/41901264550/reverse-ascii.patch"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


@contextmanager
def checkout():
    with tempfile.TemporaryDirectory(prefix="publication-guard-", dir=ROOT.parent) as temporary:
        assert Path(temporary).resolve().parent == ROOT.parent.resolve()
        root = Path(temporary) / "repo"; root.mkdir()
        git(root, "init", "--quiet")
        git(root, "config", "user.name", "No-AI contract")
        git(root, "config", "user.email", "validation@example.invalid")
        git(root, "config", "core.autocrlf", "false")
        (root / "src").mkdir(); (root / ".github").mkdir()
        (root / SOURCE).write_text((ROOT / SOURCE).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        (root / "AGENTS.md").write_text("Original instructions\n")
        (root / ".github/trusted.yml").write_text("original\n")
        git(root, "add", "."); git(root, "commit", "--quiet", "-m", "Pinned synthetic fixture")
        # Restore trusted overlays after checkout, as observed in gh-aw.
        (root / "AGENTS.md").write_text("Reviewed trusted overlay\n")
        (root / ".github/new-overlay.yml").write_text("trusted restored file\n")
        yield root


def commit_candidate(root, branch=g.NEXT_BRANCH):
    git(root, "switch", "--quiet", "-c", branch)
    git(root, "apply", "--check", str(PATCH)); git(root, "apply", str(PATCH))
    git(root, "add", "--", SOURCE)
    git(root, "commit", "--quiet", "-m", "Implement preserved reverseAscii candidate")


class PublicationGuardTests(unittest.TestCase):
    def test_valid_one_commit_and_unchanged_dirty_overlays_pass(self):
        with checkout() as root:
            before = g.snapshot(root); commit_candidate(root)
            g.compare(before, g.snapshot(root), "next", root)
            self.assertEqual(git(root, "diff", "--name-only", before["head"], "HEAD").decode().strip(), SOURCE)
            self.assertIn("AGENTS.md", git(root, "status", "--short").decode())

    def test_uncommitted_only_change_fails(self):
        with checkout() as root:
            before = g.snapshot(root)
            git(root, "switch", "--quiet", "-c", g.NEXT_BRANCH); git(root, "apply", str(PATCH))
            with self.assertRaises(ValueError): g.compare(before, g.snapshot(root), "next", root)

    def test_wrong_branch_and_extra_commit_fail(self):
        for kind in ["wrong-branch", "extra-commit"]:
            with self.subTest(kind=kind), checkout() as root:
                before = g.snapshot(root); commit_candidate(root, "wrong" if kind == "wrong-branch" else g.NEXT_BRANCH)
                if kind == "extra-commit": git(root, "commit", "--quiet", "--allow-empty", "-m", "Unauthorized second commit")
                with self.assertRaises(ValueError): g.compare(before, g.snapshot(root), "next", root)

    def test_staged_trusted_overlay_in_commit_is_rejected(self):
        with checkout() as root:
            before = g.snapshot(root)
            git(root, "switch", "--quiet", "-c", g.NEXT_BRANCH); git(root, "apply", str(PATCH))
            git(root, "add", "--", SOURCE, "AGENTS.md"); git(root, "commit", "--quiet", "-m", "Unauthorized overlay commit")
            with self.assertRaises(ValueError): g.compare(before, g.snapshot(root), "next", root)

    def test_post_commit_edits_new_files_changed_tests_or_refs_fail(self):
        for kind in ["source-edit", "extra-file", "overlay-edit", "extra-ref", "test-file"]:
            with self.subTest(kind=kind), checkout() as root:
                before = g.snapshot(root); commit_candidate(root)
                if kind == "source-edit": (root / SOURCE).write_text("uncommitted replacement\n")
                if kind == "extra-file": (root / "extra.txt").write_text("not authorized\n")
                if kind == "overlay-edit": (root / ".github/trusted.yml").write_text("tampered\n")
                if kind == "test-file": (root / "test").mkdir(); (root / "test/unauthorized.mjs").write_text("test mutation\n")
                if kind == "extra-ref": git(root, "branch", "unauthorized-ref")
                with self.assertRaises(ValueError): g.compare(before, g.snapshot(root), "next", root)

    def test_review_and_optional_repair_still_reject_commits(self):
        for stage in ["review", "repair"]:
            with self.subTest(stage=stage), checkout() as root:
                before = g.snapshot(root); commit_candidate(root)
                with self.assertRaises(ValueError): g.compare(before, g.snapshot(root), stage, root)

    def test_review_rejects_branch_only_change(self):
        with checkout() as root:
            before = g.snapshot(root)
            git(root, "switch", "--quiet", "-c", "unauthorized-review-branch")
            with self.assertRaises(ValueError): g.compare(before, g.snapshot(root), "review", root)

    def test_merge_commit_is_rejected(self):
        with checkout() as root:
            before = g.snapshot(root)
            git(root, "switch", "--quiet", "-c", "unauthorized-side")
            git(root, "commit", "--quiet", "--allow-empty", "-m", "Side commit")
            git(root, "switch", "--quiet", "--detach", before["head"])
            commit_candidate(root)
            git(root, "merge", "--quiet", "--no-ff", "unauthorized-side", "-m", "Unauthorized merge")
            with self.assertRaises(ValueError): g.compare(before, g.snapshot(root), "next", root)

    def test_candidate_is_exact_preserved_evidence_and_passes_eight_tests(self):
        provenance = json.loads((PATCH.parent / "provenance.json").read_text())
        self.assertEqual(hashlib.sha256(PATCH.read_bytes()).hexdigest(), provenance["patch_sha256"])
        with checkout() as root:
            commit_candidate(root)
            self.assertTrue(git(root, "hash-object", SOURCE).decode().strip().startswith("cfa3750"))
            (root / "test").mkdir()
            (root / "test/reverse-ascii.test.mjs").write_bytes((ROOT / "test/reverse-ascii.test.mjs").read_bytes())
            result = subprocess.run(["node", "--test", "test/reverse-ascii.test.mjs"], cwd=root, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("pass 8", result.stdout)


if __name__ == "__main__":
    unittest.main()
