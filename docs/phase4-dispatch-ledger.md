# Phase 4C — ordered dispatcher and durable reservation pilot

This change is **inert** until reviewed and merged. It adds a deterministic
reservation planner and an optional **read-only scheduled preview**, not a
paid worker dispatcher.

## What is implemented

- `scripts/phase4_dispatch.py` selects the next task from the already-reviewed
  queue; a pending coder reserves at most **33** AI credits and the independent
  reviewer at most **20**, for a combined **53-credit worst case**.
- The ledger schema is `{"version":1,"repository":"rpickett578/gh-aw-codex-pilot","claims":[]}`.
  A future, separately installed `phase4-dispatch-ledger` branch will hold
  `phase4/dispatch-ledger.json`. This PR **does not create that branch**.
- Each claim is keyed by task and stage, contains the exact run/worker/source/
  PR-head context and cannot be automatically repeated. Two attempts at the same
  stage return `HELD`, even if the earlier run failed.
- The optional `--claim` path checks reviewed main, requires a separate explicit
  installation flag, reads the ledger from that branch, and writes with the
  prior content SHA. A conflict fails closed, without retrying or launching.
- The `--preview` path runs every 15 minutes after installation and uses only
  read permissions. It never reads/writes the ledger, invokes the optional claim,
  calls Codex or dispatches any paid workflow.
- Offline regression tests cover empty/wait/repair statuses, cost accounting,
  duplicate claim, stale review head, malformed/altered ledger, insufficient
  budget and an optimistic-write conflict.

## Important remaining gates before paid pilot

1. PR #20's executable coder/reviewer locks must be exact-current-source,
   CI green, independently reviewed and merged.
2. Review the Phase 4C planner, run and pass its offline CI; then install the
   read-only scheduled preview and prove the real GitHub schedule runs.
3. Create the isolated ledger branch with an empty schema and test the
   create/update/409 conflict behavior on an isolated ledger fixture.
4. Add a **separate reviewed** root runner with an explicit claim-before-launch
   dependency and concurrency. Map `READY_CODING` and `READY_REVIEW` to
   the generic workers with exact source/PR/head, and ensure worker output
   provenance and scheduled-root review attribution are admitted.
5. Perform one bounded synthetic task only when explicitly authorized,
   with a verified credit ceiling and delivery/repair monitoring. No automatic
   repair or retry is enabled by this change.

No Call Captain source, credentials, data, ServiceTitan connection, mobile build,
release or production environment is touched by Phase 4C.
