"""Independent host-only genuine defect validation for Phase 3 repairs.

Native publication is performed ONLY by a separately compiled gh-aw workflow.
This file reads GitHub evidence and executes bounded JSON inputs against a
credential-free Node process with filesystem permissions limited to one source.
"""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from phase3_gate import TASKS, Stop, check, decide, parse_review, verified_workflow_origin
from phase3_snapshot import api, collect

CASES = {
    'ascii-vowel-count-v1': ('countAsciiVowels', 'src/ascii-vowel-count.mjs'),
    'strip-ascii-controls-v1': ('stripAsciiControls', 'src/strip-ascii-controls.mjs'),
    'collapse-ascii-spaces-v1': ('collapseAsciiSpaces', 'src/collapse-ascii-spaces.mjs'),
}


def oracle(task, value):
    if type(value) is not str:
        return {'error': 'TypeError'}
    if task == 'ascii-vowel-count-v1':
        return {'value': sum(ch in 'aeiouAEIOU' for ch in value)}
    if task == 'strip-ascii-controls-v1':
        return {'value': ''.join(ch for ch in value if ord(ch) >= 32 and ord(ch) != 127)}
    if task == 'collapse-ascii-spaces-v1':
        return {'value': re.sub(' +', ' ', value)}
    raise Stop('unknown synthetic task')


def source_at(sha, source):
    check(re.fullmatch('[0-9a-f]{40}', sha) is not None and
          source in [entry[2] for entry in TASKS], 'invalid exact source request')
    item = api('/contents/' + source + '?ref=' + sha)
    check(item.get('encoding') == 'base64' and
          isinstance(item.get('size'), int) and
          0 < item['size'] <= 16384, 'source encoding or size invalid')
    raw = base64.b64decode(item['content'], validate=False)
    check(len(raw) == item['size'], 'source bytes not matching GitHub')
    return raw


def observe(source, task, input_value):
    func, _ = CASES[task]
    check(len(source) <= 16384, 'source too large for isolated reproduction')
    with tempfile.TemporaryDirectory(prefix='phase3-reproducer-') as tmp:
        module = Path(tmp) / 'candidate.mjs'
        module.write_bytes(source)
        # The input is JSON data, NEVER shell or Python code. No environment
        # secrets reach the child process. No network/process/FS-write permission.
        runner = """import {pathToFileURL} from 'node:url';
const module = await import(pathToFileURL(process.argv[1]));
try {
const v=module[process.argv[2]](JSON.parse(process.argv[3]));
console.log(JSON.stringify({value:v}));
} catch (e) {
console.log(JSON.stringify({error:e.name}));
}"""
        env = {key: os.environ[key] for key in ('PATH', 'SystemRoot') if key in os.environ}
        p = subprocess.run(
            ['node', '--permission', '--allow-fs-read=' + str(module),
             '--input-type=module', '-e', runner,
             str(module), func, json.dumps(input_value, ensure_ascii=True)],
            cwd=tmp, env=env, capture_output=True, text=True,
            encoding='utf-8', timeout=5)
        check(p.returncode == 0 and len(p.stdout) < 2048,
              'isolated reproducer failed')
        try:
            return json.loads(p.stdout)
        except (TypeError, ValueError) as exc:
            raise Stop('unparseable isolated reproducer output') from exc


def validate_cases(task, review, original_source, repaired_source=None):
    check(review['verdict'] == 'findings', 'no genuine findings requiring a repair')
    lines = original_source.splitlines()
    check(len(review['findings']) > 0, 'empty correction request')
    seen = set()
    for case in review['findings']:
        inp = case['input']
        key = json.dumps(inp, sort_keys=True)
        check(key not in seen, 'duplicate finding input')
        seen.add(key)
        check(1 <= case['line'] <= len(lines), 'finding line outside original source')
        expected = oracle(task, inp)
        check(case['expected'] == expected, 'finding contradicts trusted task oracle')
        observed = observe(original_source, task, inp)
        check(observed != expected, 'finding does not reproduce on original source')
        if repaired_source is not None:
            check(observe(repaired_source, task, inp) == expected,
                  'repair did not fix the authentic original finding')
    return len(seen)


def find_review(snapshot, task, head):
    reviews = (snapshot.get('evidence') or {}).get(task, {}).get('reviews') or []
    matches = [r for r in reviews if r.get('commit_id') == head
               and '```phase3-review' in (r.get('body') or '')]
    check(len(matches) == 1, 'exact original review is missing or ambiguous')
    review = matches[0]
    current = snapshot.get('current_run_id')
    if current is not None:
        review_run, review_install = verified_workflow_origin(
            snapshot, review.get('body') or '', 'phase3-review',
            snapshot['install_sha'], current)
    else:
        review_run, review_install = current, snapshot['install_sha']
    data = parse_review(review, task, head, review_install, review_run)
    return review, data


def admit_before(snapshot, task, pr_number, original, review_id):
    check(task in CASES, 'task not approved')
    decision = decide(snapshot)
    check(decision.get('action') == 'REPAIR' and decision.get('task') == task and
          str(decision.get('pr')) == str(pr_number) and
          decision.get('head') == original and
          str(decision.get('review_id')) == str(review_id),
          'one approved exact-head repair not admitted')
    review, data = find_review(snapshot, task, original)
    check(str(review.get('id')) == str(review_id), 'original review id differs')
    source = source_at(original, CASES[task][1])
    validate_cases(task, data, source)
    return data, source


def admit_after(snapshot, task, pr_number, original, native_sha):
    check(task in CASES, 'task not approved')
    result = decide(snapshot)
    check(result.get('action') == 'REVIEW' and
          result.get('post_repair') is True and
          result.get('task') == task and str(result.get('pr')) == str(pr_number),
          'post-repair exact-head CI/review admission failed')
    head = result['head']
    check(re.fullmatch('[0-9a-f]{40}', native_sha) is not None,
          'native repair output missing')
    proof = snapshot['evidence'][task]['repair_proof']
    commits = proof['commits']
    check(native_sha == commits[0]['sha'] and head == commits[-1]['sha'],
          'native committed repair does not match head or its empty CI child')
    review, data = find_review(snapshot, task, original)
    check(data['verdict'] == 'findings', 'no original defect to repair')
    validate_cases(task, data, source_at(original, CASES[task][1]),
                   source_at(head, CASES[task][1]))
    return head


def main():
    check(len(sys.argv) == 3, 'usage: repair_evidence.py before|after|post task-id')
    stage, task = sys.argv[1:]
    check(stage in ('before', 'after', 'post') and task in CASES, 'invalid evidence stage')
    original = os.environ.get('ORIGINAL_HEAD', '')
    pr = os.environ.get('TARGET_PR', '')
    review_id = os.environ.get('REVIEW_ID', '')
    check(re.fullmatch('[0-9a-f]{40}', original) is not None and
          pr.isascii() and pr.isdigit() and int(pr) > 0, 'target identity missing')
    if stage == 'before':
        data, source = admit_before(collect(), task, pr, original, review_id)
        # Only independently reproduced, bounded data reaches the agent.
        location = Path('/tmp/gh-aw/phase3-authentic-findings.json')
        location.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({'task': task, 'original_head': original,
                              'pr': int(pr), 'findings': data['findings']})
        check(len(payload) <= 4096, 'evidence package too large')
        location.write_text(payload)
        location.chmod(0o400)
        print('PHASE3_GENUINE_DEFECT_CONFIRMED', task, original)
    elif stage == 'post':
        data, original_source = admit_before(collect(), task, pr, original, review_id)
        repaired = Path(CASES[task][1]).read_bytes()
        validate_cases(task, data, original_source, repaired)
        print('PHASE3_ONE_COMMITTED_SOURCE_REPAIR_VALID', task)
    else:
        head = admit_after(collect(), task, pr, original,
                           os.environ.get('NATIVE_REPAIR_SHA', ''))
        path = os.environ.get('GITHUB_OUTPUT')
        if path:
            with open(path, 'a', encoding='utf-8') as output:
                output.write('head_sha=' + head + '\n')
                output.write('pr_number=' + str(int(pr)) + '\n')
        print('PHASE3_POST_REPAIR_CI_AND_FINDINGS_PASS', task, head)


if __name__ == '__main__':
    try:
        main()
    except (Stop, KeyError, ValueError, TypeError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit('PHASE3_REPAIR_STOP: ' + str(error))
