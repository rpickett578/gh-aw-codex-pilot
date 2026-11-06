"""Pure, fail-closed decision layer for an explicitly approved 3-task pilot.

No dispatch, GitHub network, credential, or mutation capability. The reviewed
GitHub host supplies a fresh read-only JSON snapshot on stdin and must recheck
immediately before every publication.
"""
import json
import re
import sys

REPO = 'rpickett578/gh-aw-codex-pilot'
FOUNDER_ID = 313606620
TASKS = (
    (11, 'ascii-vowel-count-v1', 'src/ascii-vowel-count.mjs'),
    (12, 'strip-ascii-controls-v1', 'src/strip-ascii-controls.mjs'),
    (13, 'collapse-ascii-spaces-v1', 'src/collapse-ascii-spaces.mjs'),
)


class Stop(Exception):
    pass


def check(value, reason):
    if not value:
        raise Stop(reason)


def approval_text(sha):
    return ('APPROVE PHASE3 THREE-TASK PILOT\nINSTALL_SHA: ' + sha +
            '\nTASK_ISSUES: #11,#12,#13\nMAX_CODING_RUNS: 3' +
            '\nMAX_REPAIRS_PER_TASK: 1\nMAX_TOTAL_AI_CREDITS: 300')


def approved(comments, sha):
    hits = [c for c in comments if (c.get('body') or '').strip() == approval_text(sha)]
    check(len(hits) <= 1, 'duplicate approval')
    if not hits:
        return False
    c = hits[0]
    user = c.get('user') or {}
    check(user.get('login') == 'rpickett578' and user.get('id') == FOUNDER_ID and
          user.get('type') == 'User' and
          c.get('author_association') in ('OWNER', 'COLLABORATOR', 'MEMBER') and
          not c.get('performed_via_github_app'), 'founder approval provenance invalid')
    return True


def require_ci(head, checks, runs):
    matched = [c for c in checks if c.get('name') == 'synthetic-tests']
    check(len(matched) == 1, 'required CI missing or duplicate')
    c = matched[0]
    check(c.get('head_sha') == head and c.get('status') == 'completed' and
          c.get('conclusion') == 'success' and
          (c.get('app') or {}).get('slug') == 'github-actions', 'required CI not success')
    matched = [r for r in runs if r.get('head_sha') == head and
               r.get('path') == '.github/workflows/ci.yml']
    check(len(matched) == 1, 'CI run missing or duplicate')
    r = matched[0]
    check(r.get('event') == 'pull_request' and r.get('status') == 'completed' and
          r.get('conclusion') == 'success' and r.get('run_attempt') == 1,
          'CI run not successful first attempt')


def decide(snapshot):
    sha = snapshot.get('install_sha', '')
    check(bool(re.fullmatch(r'[a-f0-9]{40}', sha)), 'installation SHA invalid')
    check(snapshot.get('repository') == REPO and
          snapshot.get('ref') == 'refs/heads/main' and
          snapshot.get('workflow_sha') == sha and
          snapshot.get('run_attempt') == 1, 'installation identity mismatch')
    if not approved(snapshot.get('approval_comments', []), sha):
        return {'action': 'STOP', 'reason': 'FOUNDER_APPROVAL_MISSING'}
    issues = snapshot.get('issues') or []
    check(len(issues) == 3, 'issue inventory differs')
    prs = snapshot.get('pull_requests') or []
    check(len(prs) < 100, 'PR inventory pagination exceeds limit')
    # A dispatch is one-shot for a reviewed installation. A rerun or a second
    # run claiming the same installed SHA is never treated as a new approval.
    current = snapshot.get('current_run_id')
    if current is not None:
        runs = snapshot.get('chain_runs') or []
        check(len(runs) < 100, 'workflow run pagination exceeds limit')
        related = [r for r in runs if r.get('head_sha') == sha]
        check(len(related) == 1 and str(related[0].get('id')) == str(current)
              and related[0].get('run_attempt') == 1
              and related[0].get('event') == 'workflow_dispatch',
              'run is missing, duplicated, or rerun')
    refs = snapshot.get('branch_refs', {})
    for i, (issue_no, task_id, source) in enumerate(TASKS):
        issue = issues[i]
        check(issue.get('number') == issue_no and issue.get('state') == 'open' and
              'Task ID: `' + task_id + '`' in (issue.get('body') or '') and
              'Source allowlist: `' + source + '` only' in (issue.get('body') or ''),
              'approved task issue scope changed')
        branch = 'codex/phase3-' + task_id
        matches = [p for p in prs if (p.get('head') or {}).get('ref') == branch]
        check(len(matches) <= 1, 'duplicate task PR')
        if not matches:
            # Native publication may create the remote branch before the PR.
            # In that case stop; do not spawn a duplicate worker.
            check(not refs.get(task_id), 'task branch exists without Draft PR')
            return {'action': 'CODING', 'task': task_id, 'issue': issue_no,
                    'source': source, 'branch': branch}
        p = matches[0]
        head = (p.get('head') or {}).get('sha', '')
        check(bool(re.fullmatch(r'[a-f0-9]{40}', head)), 'PR head SHA invalid')
        if task_id in refs:
            check(refs[task_id] == head, 'task branch ref and Draft PR head disagree')
        check(p.get('state') == 'open' and p.get('draft') is True and
              not p.get('merged_at') and
              (p.get('head') or {}).get('repo', {}).get('full_name') == REPO and
              (p.get('base') or {}).get('repo', {}).get('full_name') == REPO and
              (p.get('base') or {}).get('ref') == 'main' and
              (p.get('user') or {}).get('login') == 'github-actions[bot]',
              'task PR not native Draft in pilot')
        details = snapshot.get('evidence', {}).get(task_id) or {}
        files = details.get('files') or []
        check(len(files) == 1 and files[0].get('filename') == source and
              files[0].get('status') == 'modified', 'PR changed unauthorized files')
        require_ci(head, details.get('checks') or [], details.get('runs') or [])
        reviews = [r for r in details.get('reviews', []) if r.get('commit_id') == head and
                   '```phase3-review' in (r.get('body') or '')]
        check(len(reviews) <= 1, 'duplicate review')
        if not reviews:
            return {'action': 'REVIEW', 'task': task_id, 'pr': p.get('number'), 'head': head}
        review = reviews[0]
        if current is not None:
            # Authenticate the native gh-aw publication marker from THIS root
            # run, not another bot COMMENT with a copied JSON payload.
            body = review.get('body') or ''
            marker = ('id: ' + str(current) + ', workflow_id: phase3-review, run: ' +
                      'https://github.com/' + REPO + '/actions/runs/' + str(current))
            call_id = '[gh-aw-workflow-call-id]: # "rpickett578%2Fgh-aw-codex-pilot%2Fphase3-review"'
            check(marker in body and call_id in body,
                  'review not published by exact hosted reviewer run')
        actor = review.get('user') or {}
        check(review.get('state') == 'COMMENTED' and
              actor.get('login') == 'github-actions[bot]' and actor.get('id') == 41898282,
              'review is not independent COMMENT publication')
        blocks = re.findall(r'```phase3-review\s*\n(.*?)\n```', review['body'], re.S)
        check(len(blocks) == 1, 'invalid review evidence')
        payload = json.loads(blocks[0])
        check(set(payload) == {'install_sha', 'task', 'head', 'verdict', 'findings'} and
              payload['install_sha'] == sha and payload['task'] == task_id and
              payload['head'] == head and payload['verdict'] in ('clean', 'findings') and
              isinstance(payload['findings'], list) and len(payload['findings']) <= 3 and
              (payload['verdict'] == 'clean') == (len(payload['findings']) == 0),
              'review evidence inconsistent')
        if payload['verdict'] == 'findings':
            return {'action': 'STOP', 'reason': 'REPAIR_NOT_YET_PROVEN',
                    'task': task_id, 'pr': p.get('number')}
    return {'action': 'STOP', 'reason': 'THREE_TASKS_COMPLETE'}


if __name__ == '__main__':
    try:
        print(json.dumps(decide(json.load(sys.stdin)), sort_keys=True))
    except (Stop, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit('STOP: ' + str(error))
