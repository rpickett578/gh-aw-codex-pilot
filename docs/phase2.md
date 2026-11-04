# Issue #3 — finite review, optional correction, one-task continuation

Recovery update: run 41880752255 consumed the original key and failed the invalid
clean-tree post-check after publishing a clean review. The activation commands
below are historical and cannot authorize another attempt. See
[the recovery-v1 procedure](phase2-recovery.md) for the separately gated replacement.

Implementation only. No Phase 2 paid execution is authorized by installation.
The original worker and exact-head synthetic-tests run now report actual GitHub
success; neither was rerun. PR #2 remains Draft and unmerged at
`f50e1a8ccc84cee5812c31938a31c93a078e7103`.

`phase2-chain.yml` uses native GitHub job dependencies and three compiled gh-aw
reusable workflows, not a dispatch agent, queue, ledger, daemon or coordinator.
Each paid job is a fresh Codex process/context on GPT-6.1 Sol / Medium. Native
gh-aw reusable-workflow artifact prefixes keep their evidence separate.

- **Review:** independent of the original worker's reasoning; pinned PR #2 head,
  diff/task/tests only. One COMMENT review with at most three inline comments;
  runtime safe-output policy enforces allowed-events=[COMMENT] and pins commit-id.
- **Correction:** only when strict review evidence reproduces a real failure.
  One source-only push, no fallback PR, no force-push, no retry. The head and exact
  original branch are rechecked before publication. Plain non-forced push fails
  on a concurrent head change. Independent reproducers must pass after the edit,
  and real PR CI must subsequently succeed on the new head.
- **Continuation:** only reverse-ascii-v1, on fixed branch
  `codex/phase2-reverse-ascii-v1`, changing only src/reverse-ascii.mjs. Its eight
  independent immutable tests and deliberately failing stub are installed first.
  Clean review, or resolved authentic findings, plus actual latest-head GitHub
  success are required before inference. Passing log text is never accepted.

There is one root attempt for the original PR-head/task key; root concurrency
serializes attempts and a bounded GitHub run-history check rejects any prior
attempt, including failure/cancellation. Called workers cannot be independently
manually dispatched. Re-runs (run_attempt > 1), changed heads/branches, ambiguous
CI/reviews, forks, unrelated files, existing next-task branch and missing evidence
all fail closed. A bounded two-minute CI admission wait reads metadata; it never
reruns CI or launches another task. The native repair SHA binds the handoff, and
the emitted dedup key includes the applicable head SHA plus task ID.

A clean review makes correction NOT APPLICABLE. It does not prove review-to-repair
execution. fixtures/seeded-defect is explicitly separate and inactive; testing
that seeded-defect scenario requires separate approval and its own branch. It is
never substituted into PR #2. No second review is hidden in the correction path:
the original finding cases are independently reconciled by deterministic tests.

## Installation and activation boundary

This Draft implementation PR must be legitimately reviewed and merged through
the existing one-human-approval and synthetic-tests protections. The CI exception
admits only the exact hashed installation on codex/phase2-issue-3 against the fixed
pre-install main. It cannot certify an implementation change to src/slugify.mjs.
After installation, ordinary PR CI admits only the old slug source (19 tests) or
the fixed next-task branch's reverse source (8 tests). No check status is forged.

After merge, first verify exact compiled locks, unchanged protections/disabled
combined Actions PR permission, only the existing encrypted OPENAI_API_KEY and
GH_AW_CI_TRIGGER_TOKEN secrets, same pilot-only Contents/Pull requests write
scope, model access, and the reviewed install commit. The root remains off until
separate execution authorization explicitly covers the finite chain and budget.

Only after that authorization, set the execution gate to the reviewed main SHA
and manually dispatch the single root (substitute the verified merged SHA):

```powershell
gh variable set PHASE2_EXECUTION_SHA --repo rpickett578/gh-aw-codex-pilot --body VERIFIED_REVIEWED_MAIN_SHA
gh workflow run phase2-chain.yml --repo rpickett578/gh-aw-codex-pilot --ref main
```

Do not execute those commands while reviewing this PR. After the one chain,
remove the authorization variable with human authorization; never rerun to hide
a failure. Each child runs automatically through native dependencies and requires
no new human prompt. Preserve actual root/job/CI/PR URLs, exact heads, review
disposition, repair reproducer results and usage artifacts. Leave all code PRs
unmerged and all human approval requirements intact.

## Cost and evidence limits

At most one reviewer + one repair worker + one next coding worker. Each has
100 AIC ($1) plus 50 AIC ($0.50) standard safety-detection guardrails, 15 model
turns (detector 3), zero retries, and no model fallback. Clean path: $3 aggregate
runtime thresholds; repair path: $4.50. Planning estimate $0.20–$0.75 under Standard
pricing, not an invoice or guaranteed ceiling; in-flight accounting can overrun
thresholds. Actions/storage are separate. No provider billing setting changes.

Local controls/compilation are implementation evidence, not a hosted Phase 2
success. The full review/correction/continuation chain remains NOT EXECUTED until
separately authorized. Automatic continuation is not claimed from a diagram.

Official contracts:
[workflow_call](https://github.github.com/gh-aw/reference/safe-outputs/#workflow-call-call-workflow),
[COMMENT-only review and source-only branch push](https://github.github.com/gh-aw/reference/safe-outputs-pull-requests/).
