export function countAsciiDigits(input) {
  if (typeof input !== 'string') {
    throw new TypeError('Expected a primitive string');
  }

  let count = 0;
  for (const character of input) {
    if (character >= '0' && character <= '9') {
      count += 1;
    }
  }
  return count;
}
