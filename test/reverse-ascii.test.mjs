import test from 'node:test';
import assert from 'node:assert/strict';
import { reverseAscii } from '../src/reverse-ascii.mjs';
for (const [input, expected] of [['', ''], ['abc', 'cba'], ['A 12!', '!21 A'], ['\0\t\n', '\n\t\0']]) {
  test(`reverses ${JSON.stringify(input)}`, () => assert.equal(reverseAscii(input), expected));
}
for (const value of [null, 42]) {
  test(`rejects non-string ${value}`, () => assert.throws(() => reverseAscii(value), TypeError));
}
for (const value of ['caf\u00e9', '\ud83d\ude00']) {
  test(`rejects non-ASCII ${JSON.stringify(value)}`, () => assert.throws(() => reverseAscii(value), RangeError));
}
