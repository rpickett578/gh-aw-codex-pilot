// Phase 3 task #11. Worker may edit only this tracked file.
export function countAsciiVowels(input) {
  if (typeof input !== 'string') {
    throw new TypeError('input must be a primitive string');
  }

  let count = 0;
  for (const character of input) {
    if ('AEIOUaeiou'.includes(character)) {
      count += 1;
    }
  }
  return count;
}
