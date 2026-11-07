import test from 'node:test';
import assert from 'node:assert/strict';
import { loadApprovedSource } from './phase4-sandbox.mjs';
const { countAsciiDigits } = await loadApprovedSource('../src/count-ascii-digits-v1.mjs');

test('empty string returns zero', () => assert.equal(countAsciiDigits(''), 0));
test('ASCII digits are counted', () => assert.equal(countAsciiDigits('0123456789'), 10));
test('digits embedded in letters and punctuation', () => assert.equal(countAsciiDigits('a1b2!3z'), 3));
test('repeated and leading zero digits', () => assert.equal(countAsciiDigits('0001200'), 7));
test('ignore letters punctuation and whitespace', () => assert.equal(countAsciiDigits('abc !\t \n xyz'), 0));
test('ignore Arabic-Indic and extended Arabic digits', () => assert.equal(countAsciiDigits('١٢٣ ۴۵۶'), 0));
test('ignore fullwidth and math Unicode digits', () => assert.equal(countAsciiDigits('１２３ 𝟏𝟐'), 0));
test('ignore emoji and non-ASCII text', () => assert.equal(countAsciiDigits('😀 café 東京'), 0));
test('mixed ASCII and non-ASCII digits', () => assert.equal(countAsciiDigits('1٢٣9４'), 2));
test('do not change or coerce primitive input', () => {
  const input = 'X1😄2 ३ Z';
  assert.equal(countAsciiDigits(input), 2);
  assert.equal(input, 'X1😄2 ३ Z');
});
for (const input of [null, undefined, 0, 5, false, [], {}, new String('12'), 12n, Symbol('digit')]) {
  test('reject non-primitive string', () => assert.throws(() => countAsciiDigits(input), e => e?.name === 'TypeError'));
}
