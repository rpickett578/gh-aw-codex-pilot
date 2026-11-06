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
    def test_orphan_branch_blocks_duplicate_coding(self):
        s=approve(snapshot())
        s['branch_refs']={gate.TASKS[0][1]: 'a'*40}
        with self.assertRaises(gate.Stop):gate.decide(s)

    def test_existing_pr_requires_matching_remote_ref(self):
        s=complete(approve(snapshot()),1)
        s['branch_refs']={gate.TASKS[0][1]: 'f'*40}
        with self.assertRaises(gate.Stop):gate.decide(s)

    def test_one_installed_run_only(self):
        s=approve(snapshot())
        s['current_run_id']='100'
        s['chain_runs']=[dict(id=100,head_sha=SHA,run_attempt=1,event='workflow_dispatch')]
        self.assertEqual(gate.decide(s)['issue'],11)
        s['chain_runs'].append(dict(id=101,head_sha=SHA,run_attempt=1,event='workflow_dispatch'))
        with self.assertRaises(gate.Stop):gate.decide(s)

    def test_rerun_denied(self):
        s=approve(snapshot())
        s['current_run_id']='100'
        s['chain_runs']=[dict(id=100,head_sha=SHA,run_attempt=2,event='workflow_dispatch')]
        with self.assertRaises(gate.Stop):gate.decide(s)

    def test_exact_native_reviewer_provenance_required(self):
        s=complete(approve(snapshot()),1)
        s['current_run_id']='100'
        s['chain_runs']=[dict(id=100,head_sha=SHA,run_attempt=1,event='workflow_dispatch')]
        with self.assertRaises(gate.Stop):gate.decide(s)
        body=s['evidence'][gate.TASKS[0][1]]['reviews'][0]['body']
        marker=('<!-- gh-aw-agentic-workflow: Phase3 Review, engine: codex, version: 0.165.0, '
                'model: openai/gpt-6.1-sol, id: 100, workflow_id: phase3-review, '
                'run: https://github.com/'+gate.REPO+'/actions/runs/100 -->')
        call='[gh-aw-workflow-call-id]: # "rpickett578%2Fgh-aw-codex-pilot%2Fphase3-review"'
        s['evidence'][gate.TASKS[0][1]]['reviews'][0]['body']=body+'\n'+marker+'\n'+call
        self.assertEqual(gate.decide(s)['issue'],12)

    def test_review_findings_select_exactly_one_bounded_repair(self):
        s=complete(approve(snapshot()),1);r=s['evidence'][gate.TASKS[0][1]]['reviews'][0]
        finding={'input':'Ae','expected':{'value':2},'line':2,'reason':'missed vowel'}
        body=json.loads(r['body'].split('phase3-review\n')[1].split('\n')[0])
        body['verdict']='findings';body['findings']=[finding]
        r['body']='```phase3-review\n'+json.dumps(body)+'\n```'
        d=gate.decide(s)
        self.assertEqual((d['action'], d['task'], d['review_id']),('REPAIR',gate.TASKS[0][1],None))

    def test_one_appended_repair_needs_exact_proof_and_second_clean_review(self):
        s=complete(approve(snapshot()),1)
        task=gate.TASKS[0][1];e=s['evidence'][task];r=e['reviews'][0]
        original=r['commit_id']
        data=json.loads(r['body'].split('phase3-review\n')[1].split('\n')[0])
        data['verdict']='findings'
        data['findings']=[{'input':'Ae','expected':{'value':2},'line':2,'reason':'missed'}]
        r['body']='```phase3-review\n'+json.dumps(data)+'\n```'
        current='f'*40
        s['pull_requests'][0]['head']['sha']=current
        e['checks'][0]['head_sha']=current;e['runs'][0]['head_sha']=current
        s['branch_refs'][task]=current
        with self.assertRaises(gate.Stop):gate.decide(s)
        e['original_ci']={'checks':[dict(e['checks'][0],head_sha=original)],
                          'runs':[dict(e['runs'][0],head_sha=original)]}
        e['repair_proof']={'status':'ahead','ahead_by':1,
            'base_commit':{'sha':original},'merge_base_commit':{'sha':original},
            'commits':[{'sha':current,'parents':[{'sha':original}]}],
            'files':[{'filename':gate.TASKS[0][2],'status':'modified'}]}
        self.assertEqual(gate.decide(s)['action'],'REVIEW')
        d2=dict(data,head=current,verdict='clean',findings=[])
        e['reviews'].append(dict(r,commit_id=current,body='```phase3-review\n'+json.dumps(d2)+'\n```'))
        self.assertEqual(gate.decide(s)['issue'],12)
        e['repair_proof']['commits'].append({'sha':'e'*40,'parents':[{'sha':current}]})
        with self.assertRaises(gate.Stop):gate.decide(s)


if __name__=='__main__':unittest.main()
