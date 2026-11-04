export function slugify(input) {
  if (typeof input !== 'string') {
    throw new TypeError('Expected a string');
  }

  return input
    .replace(/[^A-Za-z0-9]+/g, '-')
    .toLowerCase()
    .replace(/^-|-$/g, '');
}
