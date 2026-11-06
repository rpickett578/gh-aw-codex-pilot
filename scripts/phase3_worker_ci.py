"""Fail-closed functional verification for one of three synthetic worker PRs.

Always loaded from trusted BASE_SHA on main, never from the worker's branch.
"""
import os
import re
import subprocess

TASKS = {
    'codex/phase3-ascii-vowel-count-v1':
        ('src/ascii-vowel-count.mjs', 'test/ascii-vowel-count.test.mjs'),
    'codex/phase3-strip-ascii-controls-v1':
        ('src/strip-ascii-controls.mjs', 'test/strip-ascii-controls.test.mjs'),
    'codex/phase3-collapse-ascii-spaces-v1':
        ('src/collapse-ascii-spaces.mjs', 'test/collapse-ascii-spaces.test.mjs'),
}


def require(ok, reason):
    if not ok:
        raise SystemExit('PHASE3_WORKER_CI_STOP: ' + reason)


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


repository = os.environ.get('REPOSITORY', '')
base = os.environ.get('BASE_SHA', '')
head = os.environ.get('HEAD_SHA', '')
branch = os.environ.get('HEAD_BRANCH', '')
require(repository == 'rpickett578/gh-aw-codex-pilot' and
        os.environ.get('HEAD_REPOSITORY') == repository, 'fork/repository mismatch')
require(branch in TASKS, 'unapproved task branch')
require(bool(re.fullmatch(r'[0-9a-f]{40}', base)) and
        bool(re.fullmatch(r'[0-9a-f]{40}', head)), 'invalid SHA')
require(git('rev-parse', 'HEAD') == head, 'not exact checked-out head')
require(git('merge-base', base, head) == base, 'worker head not based on trusted main')
source, tests = TASKS[branch]
changed = git('diff', '--name-only', '--no-renames', base + '...' + head).splitlines()
require(changed == [source], 'worker changed another file')
require(git('cat-file', '-t', head + ':' + source) == 'blob',
        'worker source is not regular blob')
require(len(subprocess.check_output(['git', 'show', head + ':' + source])) <= 16384,
        'worker source exceeds 16KB')
result = subprocess.run(['node', '--test', '--test-reporter=tap', tests],
                        capture_output=True, text=True, timeout=45)
print(result.stdout)
require(result.returncode == 0, 'functional tests failed')
for key, count in [('tests', 11), ('pass', 11), ('fail', 0),
                   ('skipped', 0), ('cancelled', 0), ('todo', 0)]:
    require(re.search(r'^# ' + key + ' ' + str(count) + '$',
                      result.stdout, re.MULTILINE) is not None,
            'unexpected ' + key + ' test count')
print('PHASE3_WORKER_CI_PASS: ' + branch + ' exact source-only 11/11')
