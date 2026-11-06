// Phase 3 task #13. Worker may edit only this tracked file.
export function collapseAsciiSpaces(input) {
  if (typeof input !== 'string') {
    throw new TypeError('input must be a primitive string');
  }
  return input.replace(/ +/g, ' ');
}
