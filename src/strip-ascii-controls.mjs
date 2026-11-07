// Phase 3 task #12. Worker may edit only this tracked file.
export function stripAsciiControls(input) {
  if (typeof input !== 'string') {
    throw new TypeError('input must be a primitive string');
  }
  return input.replace(/[\u0000-\u001f\u007f]/g, '');
}
