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
# Immutable receipt for completed Task 1; not a new execution approval.
FIRST_INSTALL_SHA = '5580a4a864f9b6c33433a91ab354d7d6c2a92a28'
FIRST_RUN_ID = 42280771454
FIRST_PR = 15
FIRST_HEAD = 'b6732694a8621604fe9d0a2058d23ebfde897268'
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
    # The founder approved the same three tasks and 300 AIC envelope once;
    # a reviewed installer correction does not create a new scope or budget.
    allowed = {approval_text(sha), approval_text(FIRST_INSTALL_SHA)}
    hits = [c for c in comments if (c.get('body') or '').strip() in allowed]
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




def parse_review(review, task_id, head, install_sha, run_id=None):
    """Validate native COMMENT provenance and the bounded structured finding."""
    actor = review.get('user') or {}
    check(review.get('commit_id') == head and review.get('state') == 'COMMENTED'
          and actor.get('login') == 'github-actions[bot]' and actor.get('id') == 41898282,
          'review not native COMMENT at exact reviewed head')
    body = review.get('body') or ''
    if run_id is not None:
        marker = ('id: ' + str(run_id) + ', workflow_id: phase3-review, run: ' +
                  'https://github.com/' + REPO + '/actions/runs/' + str(run_id))
        call_id = '[gh-aw-workflow-call-id]: # "rpickett578%2Fgh-aw-codex-pilot%2Fphase3-review"'
        check(marker in body and call_id in body, 'review publication provenance invalid')
    blocks = re.findall(r'```phase3-review\s*\n(.*?)\n```', body, re.S)
    check(len(blocks) == 1, 'review block missing or ambiguous')
    try:
        data = json.loads(blocks[0])
    except (TypeError, ValueError) as error:
        raise Stop('invalid review JSON') from error
    check(isinstance(data, dict) and
          set(data) == {'install_sha', 'task', 'head', 'verdict', 'findings'} and
          data['install_sha'] == install_sha and data['task'] == task_id and
          data['head'] == head and data['verdict'] in ('clean', 'findings') and
          isinstance(data['findings'], list) and len(data['findings']) <= 3 and
          (data['verdict'] == 'clean') == (len(data['findings']) == 0),
          'review schema or verdict invalid')
    for item in data['findings']:
        check(isinstance(item, dict) and
              set(item) == {'input', 'expected', 'line', 'reason'} and
              type(item['line']) is int and 1 <= item['line'] <= 200 and
              isinstance(item['reason'], str) and 1 <= len(item['reason']) <= 500 and
              len(json.dumps(item['input'])) <= 256 and
              isinstance(item['expected'], dict) and
              set(item['expected']) in ({'value'}, {'error'}),
              'malformed bounded finding')
    return data


def require_repair_proof(proof, task_id, source, original, current):
    """A single appended source commit, optionally followed by empty CI trigger."""
    check(isinstance(proof, dict) and
          proof.get('status') == 'ahead' and
          proof.get('base_commit', {}).get('sha') == original and
          proof.get('merge_base_commit', {}).get('sha') == original,
          'repair not appended to original reviewed head')
    commits = proof.get('commits') or []
    check(1 <= len(commits) <= 2 and
          proof.get('ahead_by') == len(commits) and
          commits[-1].get('sha') == current,
          'multiple repairs, side history or wrong repair head')
    first = commits[0]
    check(len(first.get('parents') or []) == 1 and
          first['parents'][0].get('sha') == original,
          'repair source commit not sole child of original')
    check(len(proof.get('files') or []) == 1 and
          proof['files'][0].get('filename') == source and
          proof['files'][0].get('status') == 'modified',
          'repair changed other source files')
    if len(commits) == 2:
        last = commits[1]
        check(len(last.get('parents') or []) == 1 and
              last['parents'][0].get('sha') == first.get('sha') and
              last.get('commit', {}).get('tree', {}).get('sha') ==
              first.get('commit', {}).get('tree', {}).get('sha'),
              'second commit not native empty CI trigger')

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
        matching = [r for r in runs if str(r.get('id')) == str(current)]
        check(len(matching) == 1, 'current root workflow run missing or ambiguous')
        own = matching[0]
        check(own.get('head_sha') == sha and
              own.get('head_branch') == 'main' and
              own.get('event') == 'workflow_dispatch' and
              own.get('run_attempt') == 1 and
              (own.get('actor') or {}).get('login') == 'rpickett578' and
              (own.get('actor') or {}).get('id') == FOUNDER_ID,
              'root run has untrusted actor, ref, event or attempt')
        # Allow a bounded resume; refuse another simultaneously active chain.
        # Already-produced task PRs prevent duplicate coding.
        active = [r for r in runs if str(r.get('id')) != str(current)
                  and r.get('head_sha') == sha and
                  r.get('status') in ('queued', 'in_progress', 'waiting', 'pending')]
        check(not active, 'another active root run exists')
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
              (p.get('user') or {}).get('login') == 'rpickett578' and
              (p.get('user') or {}).get('id') == FOUNDER_ID,
              'task PR not published through the approved founder-owned native token')
        task_install = sha
        task_run = current
        if i == 0 and sha != FIRST_INSTALL_SHA:
            # Preserve the genuine completed Task 1 across an installer fix.
            # Require its exact historic PR and reviewed commit, not a name match.
            check(p.get('number') == FIRST_PR and head == FIRST_HEAD,
                  'completed Task 1 receipt changed')
            task_install = FIRST_INSTALL_SHA
            task_run = FIRST_RUN_ID
        if current is not None:
            # Actual Phase 2 gh-aw native PR publication is attributed to the
            # founder-owned token, not github-actions[bot]. Verify the native
            # workflow markers and exact root run; never infer native origin
            # from the human user identity alone.
            body = p.get('body') or ''
            workflow = 'phase3-coder-' + str(i + 1)
            check(('<!-- gh-aw-workflow-id: ' + workflow + ' -->') in body and
                  ('<!-- gh-aw-workflow-call-id: ' + REPO + '/' + workflow + ' -->') in body and
                  ('id: ' + str(task_run) + ', workflow_id: ' + workflow +
                   ', run: https://github.com/' + REPO + '/actions/runs/' +
                   str(current)) in body,
                  'native coding PR not from the exact authorized root run')
        details = snapshot.get('evidence', {}).get(task_id) or {}
        files = details.get('files') or []
        check(len(files) == 1 and files[0].get('filename') == source and
              files[0].get('status') == 'modified', 'PR changed unauthorized files')
        require_ci(head, details.get('checks') or [], details.get('runs') or [])
        all_reviews = [r for r in details.get('reviews', [])
                       if '```phase3-review' in (r.get('body') or '')]
        current_reviews = [r for r in all_reviews if r.get('commit_id') == head]
        earlier = [r for r in all_reviews if r.get('commit_id') != head]
        check(len(current_reviews) <= 1 and len(earlier) <= 1,
              'duplicate, stale or third independent review')
        if earlier:
            original = earlier[0]
            original_head = original.get('commit_id')
            check(bool(re.fullmatch(r'[a-f0-9]{40}', original_head)),
                  'invalid original reviewed head')
            initial = parse_review(original, task_id, original_head, task_install, task_run)
            check(initial['verdict'] == 'findings',
                  'clean original review followed by unauthorized code change')
            require_repair_proof(details.get('repair_proof'), task_id, source,
                                 original_head, head)
            orig_ci = details.get('original_ci') or {}
            require_ci(original_head, orig_ci.get('checks') or [],
                       orig_ci.get('runs') or [])
        if not current_reviews:
            return {'action': 'REVIEW', 'task': task_id,
                    'pr': p.get('number'), 'head': head,
                    'post_repair': bool(earlier)}
        current_review = current_reviews[0]
        data = parse_review(current_review, task_id, head, task_install, task_run)
        if data['verdict'] == 'findings':
            check(not earlier, 'second review found another defect; repair limit reached')
            return {'action': 'REPAIR', 'task': task_id,
                    'pr': p.get('number'), 'head': head,
                    'review_id': current_review.get('id')}

    return {'action': 'STOP', 'reason': 'THREE_TASKS_COMPLETE'}


if __name__ == '__main__':
    try:
        print(json.dumps(decide(json.load(sys.stdin)), sort_keys=True))
    except (Stop, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit('STOP: ' + str(error))
