import test from 'node:test';
import assert from 'node:assert/strict';
import { slugify } from '../src/slugify.mjs';

const cases = [
  ['Hello World', 'hello-world'],
  ['  HELLO   WORLD  ', 'hello-world'],
  ['One_two...THREE!', 'one-two-three'],
  ['A---B', 'a-b'],
  ['A\tB\nC', 'a-b-c'],
  ['Build 42', 'build-42'],
  ['already-normal', 'already-normal'],
  ['', ''],
  ['***', ''],
  ['caf\u00e9 noir', 'caf-noir'],
  ['\u0130\u212a', ''],
  ['\u00e9A\u00e9', 'a'],
];
for (const [input, expected] of cases) {
  test(`normalizes ${JSON.stringify(input)}`, () => {
    assert.equal(slugify(input), expected);
  });
}
for (const input of [null, undefined, 42, true, {}, [], new String('hello')]) {
  test(`rejects non-string ${Object.prototype.toString.call(input)}`, () => {
    assert.throws(() => slugify(input), TypeError);
  });
}
