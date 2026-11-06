"""Bounded read-only admission wait after native PR or COMMENT publication.

No retries of workers or CI, no API writes, and no self-approval.
"""
import json
import os
import sys
import time
from phase3_gate import Stop, decide, require_ci, TASKS
from phase3_snapshot import collect
from phase3_repair_evidence import admit_after

TASK_IDS = {task for _, task, _ in TASKS}
TRANSIENT = (
    'required CI missing or duplicate',
    'required CI not success',
    'CI run missing or duplicate',
    'CI run not successful first attempt',
    'task branch exists without Draft PR',
)


def require(value, message):
    if not value:
        raise Stop(message)


def terminal_failed_ci(snapshot, task_id):
    e = snapshot.get('evidence', {}).get(task_id) or {}
    checks = e.get('checks') or []
    runs = e.get('runs') or []
    if any(c.get('name') == 'synthetic-tests' and c.get('status') == 'completed'
           and c.get('conclusion') != 'success' for c in checks):
        return True
    return any(r.get('status') == 'completed' and r.get('conclusion') != 'success'
               for r in runs)


def output(**items):
    path = os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a', encoding='utf-8') as stream:
            for key, val in items.items():
                stream.write(str(key) + '=' + str(val) + '\n')


def main():
    require(len(sys.argv) == 3, 'usage: phase3_wait.py review-ready|repair-ready|next-ready|complete task_id')
    mode, task_id = sys.argv[1:]
    require(mode in ('review-ready', 'repair-ready', 'next-ready', 'complete') and task_id in TASK_IDS,
            'unexpected gate transition')
    expected_pr = os.environ.get('EXPECTED_PR', '')
    if mode == 'review-ready':
        require(expected_pr.isascii() and expected_pr.isdigit() and int(expected_pr) > 0,
                'native PR publication output missing')
        require(os.environ.get('EXPECTED_URL') ==
                'https://github.com/rpickett578/gh-aw-codex-pilot/pull/' + expected_pr,
                'native PR URL differs')
    if mode == 'repair-ready':
        expected_pr = os.environ.get('TARGET_PR', '')
        require(expected_pr.isascii() and expected_pr.isdigit() and int(expected_pr) > 0,
                'repaired target PR number missing')
        require(len(os.environ.get('ORIGINAL_HEAD', '')) == 40 and
                len(os.environ.get('NATIVE_REPAIR_SHA', '')) == 40,
                'original and published native commit SHAs mandatory')
    require(os.environ.get('PHASE3_CHAIN_RUN_ID') == os.environ.get('GITHUB_RUN_ID'),
            'not the exact root workflow run')

    for attempt in range(18):
        snapshot = collect()
        try:
            result = decide(snapshot)
        except Stop as error:
            reason = str(error)
            if reason not in TRANSIENT or terminal_failed_ci(snapshot, task_id):
                raise
            result = {'action': 'PENDING', 'reason': reason}
        if mode == 'repair-ready':
            if result.get('action') == 'REVIEW' and result.get('task') == task_id and result.get('post_repair'):
                head = admit_after(snapshot, task_id, expected_pr,
                                   os.environ['ORIGINAL_HEAD'],
                                   os.environ['NATIVE_REPAIR_SHA'])
                output(pr_number=expected_pr, head_sha=head, task_id=task_id)
                print('PHASE3_REPAIRED_HEAD_REVIEW_READY', task_id, head)
                return
        action = result.get('action')
        if mode == 'review-ready' and action == 'REVIEW':
            require(result.get('task') == task_id and
                    str(result.get('pr')) == expected_pr and
                    len(result.get('head', '')) == 40,
                    'review candidate not the exact native PR')
            output(pr_number=expected_pr, head_sha=result['head'], task_id=task_id)
            print('PHASE3_REVIEW_READY ' + task_id + ' #' + expected_pr + ' ' + result['head'])
            return
        if mode == 'next-ready' and action == 'CODING':
            require(result.get('task') == task_id, 'next task reordered')
            output(task_id=task_id, issue=result['issue'])
            print('PHASE3_NEXT_READY ' + task_id)
            return
        if mode == 'complete' and action == 'STOP' and result.get('reason') == 'THREE_TASKS_COMPLETE':
            print('PHASE3_THREE_TASKS_COMPLETE')
            return
        if action == 'STOP':
            raise Stop('terminal queue stop: ' + str(result.get('reason')))
        if action not in ('CODING', 'REVIEW', 'PENDING'):
            raise Stop('unrecognized admission state')
        if attempt == 17:
            raise Stop('read-only admission window exceeded; no automatic retry')
        time.sleep(10)


if __name__ == '__main__':
    try:
        main()
    except (Stop, KeyError, TypeError, ValueError) as error:
        raise SystemExit('PHASE3_STOP: ' + str(error))
