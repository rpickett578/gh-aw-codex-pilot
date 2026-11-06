"""Offline trusted-oracle and actual Git repair-guard regressions.

No GitHub credentials, hosted AI, network or production repository are used.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from phase3_gate import Stop
from phase3_repair_evidence import oracle, observe, validate_cases
from phase3_workspace_guard import snapshot, compare

ORIGINAL = b"""export function countAsciiVowels(input) {
if (typeof input !== 'string') throw new TypeError('string required');
return 0;
}
"""
FIXED = b"""export function countAsciiVowels(input) {
if (typeof input !== 'string') throw new TypeError('string required');
return (input.match(/[aeiou]/gi) || []).length;
}
"""


def finding(value='AE'):
    return {'verdict': 'findings', 'findings': [
        {'input': value, 'expected': oracle('ascii-vowel-count-v1', value),
         'line': 3, 'reason': 'the original returns zero for any vowel'}]}


class GenuineFindings(unittest.TestCase):
    def test_oracles_are_ascii_only(self):
        self.assertEqual(oracle('ascii-vowel-count-v1', 'AéIéOu'), {'value': 4})
        self.assertEqual(oracle('strip-ascii-controls-v1', 'a\tb\nc\x7fd é'),
                         {'value': 'abcd é'})
        self.assertEqual(oracle('collapse-ascii-spaces-v1', '  x \t   y  '),
                         {'value': ' x \t y '})
        self.assertEqual(oracle('ascii-vowel-count-v1', None), {'error': 'TypeError'})

    @unittest.skipUnless(shutil.which('node'), 'Node is mandatory in hosted CI')
    def test_actual_unprivileged_node_reproducer(self):
        self.assertEqual(observe(ORIGINAL, 'ascii-vowel-count-v1', 'AE'), {'value': 0})
        self.assertEqual(observe(FIXED, 'ascii-vowel-count-v1', 'AE'), {'value': 2})
        self.assertEqual(validate_cases('ascii-vowel-count-v1', finding(),
                                        ORIGINAL, FIXED), 1)

    @unittest.skipUnless(shutil.which('node'), 'Node is mandatory in hosted CI')
    def test_reject_contradictory_and_nonreproducing_findings(self):
        wrong = finding()
        wrong['findings'][0]['expected'] = {'value': 100}
        with self.assertRaises(Stop):
            validate_cases('ascii-vowel-count-v1', wrong, ORIGINAL)
        with self.assertRaises(Stop):
            validate_cases('ascii-vowel-count-v1', finding(), FIXED)
        with self.assertRaises(Stop):
            validate_cases('ascii-vowel-count-v1', finding(), ORIGINAL, ORIGINAL)
        duplicate=finding()
        duplicate['findings'] *= 2
        with self.assertRaises(Stop):
            validate_cases('ascii-vowel-count-v1', duplicate, ORIGINAL)

    def test_invalid_source_line_fails(self):
        case = finding()
        case['findings'][0]['line'] = 500
        with self.assertRaises(Stop):
            validate_cases('ascii-vowel-count-v1', case, ORIGINAL)


class GitCommitGuard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='phase3-real-git-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Phase3 Offline Test')
        self.git('config', 'user.email', 'offline@example.invalid')
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'ascii-vowel-count.mjs').write_bytes(ORIGINAL)
        (self.root / 'README.md').write_text('immutable\n')
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'baseline')
        self.original = self.git('rev-parse', 'HEAD')
        self.git('checkout', '--detach', '-q', 'HEAD')
        self.before = snapshot(self.root)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args],
                                       stderr=subprocess.DEVNULL, text=True).strip()

    def repair(self):
        self.git('switch', '-q', '-c', 'codex/phase3-ascii-vowel-count-v1')
        (self.root / 'src' / 'ascii-vowel-count.mjs').write_bytes(FIXED)
        self.git('add', 'src/ascii-vowel-count.mjs')
        self.git('commit', '-q', '-m', 'single authentic repair')

    def test_valid_exact_source_only_commit(self):
        self.repair()
        compare(self.before, snapshot(self.root), 'repair-1', self.root)

    def test_uncommitted_only_is_rejected(self):
        (self.root / 'src' / 'ascii-vowel-count.mjs').write_bytes(FIXED)
        with self.assertRaises(ValueError):
            compare(self.before, snapshot(self.root), 'repair-1', self.root)

    def test_extra_commit_is_rejected(self):
        self.repair()
        (self.root / 'src' / 'ascii-vowel-count.mjs').write_bytes(FIXED + b'\n// extra\n')
        self.git('add', 'src/ascii-vowel-count.mjs')
        self.git('commit', '-q', '-m', 'second')
        with self.assertRaises(ValueError):
            compare(self.before, snapshot(self.root), 'repair-1', self.root)

    def test_wrong_branch_is_rejected(self):
        self.git('switch', '-q', '-c', 'codex/not-approved')
        (self.root / 'src' / 'ascii-vowel-count.mjs').write_bytes(FIXED)
        self.git('add', 'src/ascii-vowel-count.mjs')
        self.git('commit', '-q', '-m', 'wrong')
        with self.assertRaises(ValueError):
            compare(self.before, snapshot(self.root), 'repair-1', self.root)

    def test_additional_file_is_rejected(self):
        self.repair()
        (self.root / 'README.md').write_text('changed\n')
        with self.assertRaises(ValueError):
            compare(self.before, snapshot(self.root), 'repair-1', self.root)


if __name__ == '__main__':
    unittest.main()
