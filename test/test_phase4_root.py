"""Offline proof that Phase4 root jobs cannot launch paid agents yet."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/phase4-chain.yml"


def job(text, name):
    found = re.search(r"^  " + re.escape(name) +
                      r":\n(.*?)(?=^  [a-z_]+:\n|\Z)",
                      text, re.M | re.S)
    if not found:
        raise AssertionError("missing required job " + name)
    return found.group(1)


class RootWorkflowTests(unittest.TestCase):
    def test_pilot_root_has_schedule_and_manual_trigger(self):
        text = WORKFLOW.read_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("cron: '*/15 * * * *'", text)
        self.assertIn("cancel-in-progress: false", text)

    def test_reservation_and_both_paid_workers_are_hard_disabled(self):
        text = WORKFLOW.read_text()
        for name in ("reserve", "coder", "reviewer"):
            with self.subTest(job=name):
                self.assertIn("if: ${{ false && ", job(text, name))

    def test_only_preview_can_run_unauthorized(self):
        text = WORKFLOW.read_text()
        inspect = job(text, "preview")
        self.assertIn("phase4_dispatch.py --preview", inspect)
        self.assertIn("contents: read", inspect)
        self.assertNotIn("contents: write", inspect)
        self.assertNotIn("--claim", inspect)
        self.assertNotIn("uses: ./.github/workflows/phase4-coder", inspect)

    def test_future_worker_dependencies_are_on_durable_reservation(self):
        text = WORKFLOW.read_text()
        for name in ("coder", "reviewer"):
            self.assertIn("needs: reserve", job(text, name))
        self.assertIn("phase4_dispatch.py --claim", job(text, "reserve"))
        self.assertIn("RESERVED_NO_WORKER_LAUNCH", job(text, "reserve"))
        self.assertIn("source_path:", job(text, "coder"))
        self.assertIn("head_sha:", job(text, "reviewer"))
        self.assertIn("needs.reserve.outputs.action == 'READY_CODING'", job(text, "coder"))
        self.assertIn("needs.reserve.outputs.action == 'READY_REVIEW'", job(text, "reviewer"))


if __name__ == "__main__":
    unittest.main()
