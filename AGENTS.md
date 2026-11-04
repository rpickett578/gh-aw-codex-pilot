# Isolated synthetic pilot

This repository contains synthetic code only. Phase 1 and the Issue #3 correction
worker may change only `src/slugify.mjs`. The separate approved next task
reverse-ascii-v1 may change only `src/reverse-ascii.mjs` and submit one Draft PR.
The independent reviewer publishes only COMMENT reviews and bounded inline
findings; it may not publish code. Tests, task descriptions, this file, scripts,
fixtures and .github are immutable for every AI worker. Human-authorized workflow
installation is a separate reviewed implementation task.
Use Node's built-in test runner. No installs, network requests, secrets inspection,
subagents, production access, merges, deployment, or external repository access.
An independent human must inspect the exact PR head and CI before acceptance.
