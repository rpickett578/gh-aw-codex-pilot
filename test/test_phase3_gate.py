"""No network/token/publisher regression tests for Phase 3."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location('gate', Path(__file__).resolve().parents[1] / 'scripts' / 'phase3_gate.py')
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)
SHA = 'a' * 40


def snapshot():
    return dict(install_sha=SHA, workflow_sha=SHA, repository=gate.REPO,
                ref='refs/heads/main', run_attempt=1, approval_comments=[],
                issues=[dict(number=n,state='open',body=f'Task ID: `{task}`\nSource allowlist: `{src}` only')
                        for n,task,src in gate.TASKS], pull_requests=[], evidence={})


def approve(s):
    s['approval_comments']=[dict(body=gate.approval_text(SHA),
       user=dict(login='rpickett578',id=313606620,type='User'), author_association='OWNER')]
    return s


def complete(s, count, include_review=True):
    for n,task,src in gate.TASKS[:count]:
        head = str(n % 10) * 40
        pr=dict(number=n+100,state='open',draft=True,head=dict(ref='codex/phase3-'+task,
            sha=head,repo=dict(full_name=gate.REPO)),base=dict(ref='main',repo=dict(full_name=gate.REPO)),
            user=dict(login='github-actions[bot]'))
        s['pull_requests'].append(pr)
        evidence=dict(files=[dict(filename=src,status='modified')],
            checks=[dict(name='synthetic-tests',head_sha=head,status='completed',conclusion='success',app=dict(slug='github-actions'))],
            runs=[dict(path='.github/workflows/ci.yml',head_sha=head,event='pull_request',status='completed',conclusion='success',run_attempt=1)],
            reviews=[])
        if include_review:
            payload=dict(install_sha=SHA,task=task,head=head,verdict='clean',findings=[])
            evidence['reviews']=[dict(commit_id=head,state='COMMENTED',user=dict(login='github-actions[bot]',id=41898282),
                         body='```phase3-review\n'+json.dumps(payload)+'\n```')]
        s['evidence'][task]=evidence
    return s


class GateTests(unittest.TestCase):
    def test_missing_approval_fails_closed(self):
        self.assertEqual(gate.decide(snapshot())['reason'],'FOUNDER_APPROVAL_MISSING')
    def test_untrusted_approval_fails(self):
        s=approve(snapshot());s['approval_comments'][0]['user']['id']=0
        with self.assertRaises(gate.Stop):gate.decide(s)
    def test_duplicate_approval_fails(self):
        s=approve(snapshot());s['approval_comments']*=2
        with self.assertRaises(gate.Stop):gate.decide(s)
    def test_invalid_ref_fails(self):
        s=approve(snapshot());s['ref']='refs/heads/other'
        with self.assertRaises(gate.Stop):gate.decide(s)
    def test_picks_first_task(self):
        self.assertEqual(gate.decide(approve(snapshot()))['issue'],11)
    def test_picks_second_after_first_review_and_ci(self):
        self.assertEqual(gate.decide(complete(approve(snapshot()),1))['issue'],12)
    def test_picks_third_after_second(self):
        self.assertEqual(gate.decide(complete(approve(snapshot()),2))['issue'],13)
    def test_empty_queue_stops(self):
        self.assertEqual(gate.decide(complete(approve(snapshot()),3))['reason'],'THREE_TASKS_COMPLETE')
    def test_review_stage_when_missing(self):
        self.assertEqual(gate.decide(complete(approve(snapshot()),1,False))['action'],'REVIEW')
    def test_pending_ci_stops(self):
        s=complete(approve(snapshot()),1);s['evidence'][gate.TASKS[0][1]]['checks'][0]['status']='queued'
        with self.assertRaises(gate.Stop):gate.decide(s)
    def test_wrong_source_stops(self):
        s=complete(approve(snapshot()),1);s['evidence'][gate.TASKS[0][1]]['files'][0]['filename']='test/evil.mjs'
        with self.assertRaises(gate.Stop):gate.decide(s)
    def test_duplicate_pr_stops(self):
        s=complete(approve(snapshot()),1);s['pull_requests']*=2
        with self.assertRaises(gate.Stop):gate.decide(s)
    def test_review_findings_stop_for_explicit_repair_gate(self):
        s=complete(approve(snapshot()),1);r=s['evidence'][gate.TASKS[0][1]]['reviews'][0]
        r['body']=r['body'].replace('"verdict": "clean", "findings": []','"verdict": "findings", "findings": [{"input": "x"}]')
        self.assertEqual(gate.decide(s)['reason'],'REPAIR_NOT_YET_PROVEN')


if __name__=='__main__':unittest.main()
