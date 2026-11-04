// Explicit, independent synthetic next-task stub; not part of PR #2.
export function reverseAscii(input) {
  if (typeof input !== 'string') {
    throw new TypeError('Expected a primitive string');
  }
  if (/[^\x00-\x7F]/.test(input)) {
    throw new RangeError('Expected only ASCII characters');
  }
  return input.split('').reverse().join('');
}
