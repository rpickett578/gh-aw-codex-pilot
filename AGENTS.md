# Isolated synthetic pilot

This repository contains synthetic code only. The coding worker may change only
`src/slugify.mjs` and submit one draft PR through gh-aw safe outputs.
Tests, TASK.md, this file, and .github are immutable for the worker.
Use Node's built-in test runner. No installs, network requests, secrets inspection,
subagents, production access, merges, deployment, or external repository access.
An independent human must inspect the exact PR head and CI before acceptance.
