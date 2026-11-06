import test from 'node:test';
import assert from 'node:assert/strict';
import { countAsciiVowels } from '../src/ascii-vowel-count.mjs';
test('empty', () => assert.equal(countAsciiVowels(''), 0));
test('mixed ASCII case', () => assert.equal(countAsciiVowels('aEiOu AEIOU'), 10));
test('consonants and digits', () => assert.equal(countAsciiVowels('xyz 123'), 0));
test('non-ASCII ignored', () => assert.equal(countAsciiVowels('éáØÜ'), 0));
test('punctuation', () => assert.equal(countAsciiVowels('A!!E'), 2));
for (const input of [null, 0, true, [], {}, new String('a')]) {
  test('reject non-primitive string: ' + String(input), () => assert.throws(() => countAsciiVowels(input), TypeError));
}
