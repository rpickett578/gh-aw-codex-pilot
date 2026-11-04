# Fix ASCII slug normalization

Implement `slugify(input)` for strings: lowercase ASCII A-Z, replace each maximal
run of characters other than ASCII a-z or 0-9 with one hyphen, and remove leading
and trailing hyphens. Empty input and input with no ASCII alphanumerics return an
empty string. Treat non-ASCII characters as separators; do not transliterate.
Throw TypeError for every non-string input. No dependencies.

Change only src/slugify.mjs. The tests intentionally fail on the initial commit.
