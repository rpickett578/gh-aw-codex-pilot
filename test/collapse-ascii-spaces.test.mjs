import test from 'node:test';
import assert from 'node:assert/strict';
import { collapseAsciiSpaces } from '../src/collapse-ascii-spaces.mjs';
test('empty', () => assert.equal(collapseAsciiSpaces(''), ''));
test('collapse groups', () => assert.equal(collapseAsciiSpaces('a    b   c'), 'a b c'));
test('preserve one space at boundaries', () => assert.equal(collapseAsciiSpaces('  a  b   '), ' a b '));
test('do not alter tabs or newlines', () => assert.equal(collapseAsciiSpaces('a\t  b\n  c'), 'a\t b\n c'));
test('preserve unicode', () => assert.equal(collapseAsciiSpaces('é  😀'), 'é 😀'));
for (const input of [null, 0, true, [], {}, new String('a')]) {
  test('reject non-primitive string: ' + String(input), () => assert.throws(() => collapseAsciiSpaces(input), TypeError));
}
