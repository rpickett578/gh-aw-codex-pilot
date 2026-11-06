# Phase 3 — bounded three-task synthetic pilot (NOT YET EXECUTED)

Updated 2026-11-06. Draft PR #14 contains a finite GitHub-native continuation graph;
it does not touch Call Captain production, Dot, the production app, or customer data.

## Actual implemented scope

- Founder-gated read-only selector: Issue #10 plus candidate Issues #11, #12, #13.
- `phase3-chain.yml`: three sequential native Codex coder calls, each followed by
  actual GitHub CI check admission and separate independent COMMENT-only review.
  GitHub schedules the next coder only after the previous exact-head review is clean.
- Three static one-file worker gh-aw sources and pinned generated locks, plus one
  dynamic-target reviewer source and pinned generated lock.
- Compiled using official gh-aw v1.0.1, with GPT-6.1 Sol / Medium, no fallback,
  zero retries, no network and per-stage bounds.
- Native Draft PR publication only; one ordinary local source commit per coder,
  no automated merge, approval, production operation or deployment.
- Host-only source, ref and index guard. Source-only functional CI uses the trusted
  base-branch verifier and 11 tests per task.
- Bounded read-only metadata waits (up to 18 observations, ten seconds apart).
  Missing/failed CI, changed branches/heads, unauthorized task, duplicate run,
  malformed review or empty queue stops the chain. No retry of an AI job.
- Exact founder-only issue comment tied to reviewed installed main SHA is required
  before any paid call. One root workflow_dispatch per installation SHA; concurrent
  root runs are serialized and subsequent runs fail the one-shot admission.

## Hosted evidence

- Earlier Phase 2 real chain: run 41913643056 / Draft PR #9, kept unchanged.
- Official gh-aw compilation of four workflows: run 42262622344.
- Hosted installer CI, 18 regression tests, all four workflow compilations,
  pinned actionlint v1.7.7 for root and preflight: run 42263369900, PASS.
- The exact generated coder/reviewer workflow SHA-256 hashes are retained in
  `scripts/verify-phase3-install.py`, checked for complete non-partial installation.
- Historical interim commits with failing CI do not constitute accepted state.
  Only latest exact-head checks qualify for review.

## Limits and remaining proof

**No Phase 3 hosted Codex execution has been dispatched yet.** Thus there are
no Phase 3 worker PRs, reviewer publications or full unattended three-task run.
Compiler/actionlint/CI checks are installation evidence, not live continuation.

**Authentic review findings currently STOP:** `REPAIR_NOT_YET_PROVEN`.
The previous Phase 2 uncommitted-vs-native committed repair mismatch is not
silently bypassed. At most one evidence-based repair must be implemented,
compiled, independently tested and admitted before calling automatic correction
proven. A clean-path pilot could be separately approved while preserving this
fail-closed boundary.

Cost configuration for the clean path is a finite 3 * (25 coder + 8 detection +
15 review + 8 detection) = **168 maximum configured AIC units**; this is an
upper bound on configured stage budgets, not an API invoice guarantee. Issue #10
sets 300 AIC maximum for a future broader test, which is NOT authorization to
spend it.

## Authority and activation

Keep Draft PR #14 unmerged until an independent human reviews its exact head
and required CI. The founder must explicitly authorize any merge. Only after
a reviewed installation is merged to main can the founder explicitly authorize
one paid Phase 3 run: exact INSTALL_SHA, candidate Issues #11–#13, limits and
root workflow. Preserve founder approval for production, releases and merges.

No new credentials or broadened GitHub PAT scopes are requested. The existing
GH_AW_CI_TRIGGER_TOKEN cannot push workflow-file updates directly; official
compiled locks were instead installed into this Draft PR using the already
authorized connected GitHub capability, then rechecked by CI.

Dot is never part of engineering scheduling or worker execution.
