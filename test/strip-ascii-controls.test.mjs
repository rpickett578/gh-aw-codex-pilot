import test from 'node:test';
import assert from 'node:assert/strict';
import { stripAsciiControls } from '../src/strip-ascii-controls.mjs';
test('empty', () => assert.equal(stripAsciiControls(''), ''));
test('remove C0 controls', () => assert.equal(stripAsciiControls('A\u0000B\tC\nD'), 'ABCD'));
test('remove DEL', () => assert.equal(stripAsciiControls('x\u007fy'), 'xy'));
test('preserve spaces and non-ASCII', () => assert.equal(stripAsciiControls(' a é😀 '), ' a é😀 '));
test('preserve printable ASCII', () => assert.equal(stripAsciiControls('A !~'), 'A !~'));
for (const input of [null, 0, true, [], {}, new String('a')]) {
  test('reject non-primitive string: ' + String(input), () => assert.throws(() => stripAsciiControls(input), TypeError));
}
