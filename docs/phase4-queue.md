# Phase 4 — persistent engineering queue (pilot foundation)

**Goal:** Replace a fixed three-task launch with one ordered source of approved work and durable GitHub evidence. The founder approves the **task scope**, not every worker transition.

## Queue control plane

- `phase4/queue.json` is the single ordered queue on the **pilot's reviewed main branch**. Reordering, appending, or updating tasks happens through a normal reviewed PR/merge. No repetitive per-run founder comment.
- Each new task contains a unique `id`, open GitHub `issue`, `allowed_files`, and `max_ai_credits`. Example:
  ```json
  {"id":"pilot-next-v1","issue":19,"allowed_files":["src/pilot-next-v1.mjs"],"max_ai_credits":60}
  ```
- Historic completed Task 1/2/3 are included with immutable `receipt` (Draft PR number and exact head SHA) and zero remaining credit authorization. They are **not rerun**.
- `scripts/phase4_queue.py` reads the queue and **live GitHub Issue, PR, CI, and structured review records**. It returns the first outstanding state: `READY_CODING`, `WAIT_CI`, `READY_REVIEW`, `READY_REPAIR`, or `QUEUE_EMPTY`. It rejects ambiguous/doubled states, altered receipts and failed CI instead of skipping tasks.
- `phase4-queue-status.yml` runs the selector on queue-related main pushes or manual dispatches, with **read-only** GitHub permissions and bounded retries for transient GitHub 502/503/504. No Codex, secrets mutation, merge, production or paid dispatch.

## Next implementation stage

Wire the approved queue selector to **one reusable Codex coding/review/repair worker pipeline** instead of three hardcoded synthetic task slots. A persistent job-state/cost ledger must prevent double dispatch and reuse prior real reviews and PRs after interruptions. Use controlled periodic GitHub scheduling after successful synthetic end-to-end acceptance, so approved tasks can continue while the founder is offline.

The main-branch manifest provides durable approval; **the next stage must not silently treat this read-only status workflow as a production-ready 24/7 dispatcher.** Preserve the existing Phase 3 workflows and Call Captain production isolation until the generic pipeline is tested.

## Generic coder/reviewer pilot envelope

The compiled Stage 4B coder caps agent + detector at **33 AI credits**; the independent reviewer caps at **20**. A new task must approve at least **53 credits total** before either paid stage may begin. Actual consumption may be lower. This approval covers both stages once, not 53 credits each. The scheduled dispatcher and historical per-stage ledger are not installed yet; this source/compile PR does **not** activate paid execution.
