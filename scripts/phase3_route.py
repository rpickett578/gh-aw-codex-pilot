"""Route one independently reviewed synthetic task without guessing a defect.

A native COMMENT is evidence, never approval. Only a host-reproduced authentic
finding produces a single repair admission; a clean review moves to next task.
"""
import os
import sys
from phase3_gate import TASKS, Stop, check, decide
from phase3_snapshot import collect
from phase3_repair_evidence import admit_before


def output(**items):
    where = os.environ.get('GITHUB_OUTPUT')
    if where:
        with open(where, 'a', encoding='utf-8') as stream:
            for key, value in items.items():
                stream.write(key + '=' + str(value) + '\n')


def main():
    check(len(sys.argv) == 2 and sys.argv[1] in (t[1] for t in TASKS),
          'unknown route task')
    task = sys.argv[1]
    snapshot = collect()
    result = decide(snapshot)
    i = [t[1] for t in TASKS].index(task)
    next_task = TASKS[i + 1][1] if i + 1 < len(TASKS) else None
    if result.get('action') == 'REPAIR' and result.get('task') == task:
        head = result['head']
        pr = result['pr']
        review_id = result['review_id']
        check(type(review_id) is int and review_id > 0, 'native review ID absent')
        admit_before(snapshot, task, pr, head, review_id)
        output(repair='true', pr_number=pr, original_head=head,
               review_id=review_id)
        print('PHASE3_ROUTE_ONE_AUTHENTIC_REPAIR', task, review_id)
        return
    if next_task is not None:
        check(result.get('action') == 'CODING' and
              result.get('task') == next_task, 'clean review did not unlock next task')
    else:
        check(result == {'action': 'STOP', 'reason': 'THREE_TASKS_COMPLETE'},
              'last clean review did not complete queue')
    reviews = snapshot.get('evidence', {}).get(task, {}).get('reviews', [])
    check(any(r.get('state') == 'COMMENTED' and
              '```phase3-review' in (r.get('body') or '')
              for r in reviews), 'independent review missing')
    output(repair='false')
    print('PHASE3_ROUTE_CLEAN', task)


if __name__ == '__main__':
    try:
        main()
    except (Stop, KeyError, TypeError, ValueError, StopIteration) as error:
        raise SystemExit('PHASE3_ROUTE_STOP: ' + str(error))
