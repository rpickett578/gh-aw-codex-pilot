# Phase 3 — finite three-task GitHub Actions + Codex pilot (UNEXECUTED)

**November 6, 2026.** The only target is `rpickett578/gh-aw-codex-pilot`.
No changes to Call Captain production, Dot, TestFlight, credentials or customer data.

## Installed in Draft PR #14

- Candidate Issues #11, #12, #13 in strict order, with Issue #10 as the
  exact-main-SHA founder-authored execution approval gate.
- Root `phase3-chain.yml` invokes three source-only native Codex workers,
  independently validates each Draft PR's actual passing GitHub CI,
  publishes a separate COMMENT-only review, and invokes the next task
  only after clean exact-head review evidence.
- **One conditional correction per task:** a genuine, independently
  reproducible reviewer finding is verified against the pinned original
  source with a trusted task-specific oracle and credential-free Node
  process. The correction worker may create **one appended non-merge commit**
  to the original PR source only. Native gh-aw
  `push-to-pull-request-branch` performs append-only publication.
- After publication, the host requires exact native repair commit ancestry,
  at most one extra empty CI-trigger commit, unchanged authorized scope,
  actual passing CI on the updated PR head, and resolution of all original
  findings. The revised head receives a second independent COMMENT review.
  If that review finds another issue, **STOP**, no second repair.
- Real-Git checkout/HEAD/index/branch/file guards reject uncommitted-only
  edits, extra commits, wrong refs, unauthorized files and other drift.
- Seven worker/reviewer/repair sources compiled by pinned official
  gh-aw v1.0.1; their exact generated locks are SHA-256 pinned by
  `scripts/verify-phase3-install.py`. Root and preflight pass
  pinned actionlint v1.7.7.
- All native generated worker PRs remain **Draft**, unmerged and unapproved.
  No self-dispatch, force push, merge, production deployment or release.

## Verified evidence (distinguish from live pilot)

- Phase 2 real baseline: [run 41913643056](https://github.com/rpickett578/gh-aw-codex-pilot/actions/runs/41913643056)
  and Draft PR #9 remain unchanged.
- [Run 42267329203](https://github.com/rpickett578/gh-aw-codex-pilot/actions/runs/42267329203)
  succeeded: **19 queue/review/repair-admission tests**, **9 independently
  run local real-Git and credential-free reproduction tests**, **7 compiled
  gh-aw workflows**, and **root actionlint PASS**.
- The compiled repair sources are installed on Draft PR #14 from official
  compiler artifacts, with hashes checked against original GitHub logs.
  Only a successful latest-head CI validates the final installation.

**Not yet proven:** native repair publisher's full authenticated gateway/push
and updated-head CI in a real paid worker run; three actual unattended coder
PRs and reviews; reliable recovery after external failures. Offline native
incremental contract was previously audited in Phase 2 and requires a
committed repair; Phase 3 uses committed append-only edits but has not yet
performed real remote repair publication.

## Budget and authority

Coder+detector: 3 x (25+8) = 99 AIC.
Independent first reviewer+detector: 3 x (15+8) = 69 AIC.
Optional one repair+detector per task: 3 x (15+8) = 69 AIC.
Optional second reviewer+detector for every repaired task: 3 x (15+8) = 69 AIC.
The full configured worst case is **306 AIC**, which **exceeds** the
Issue #10 stated 300 AIC pilot cap. Therefore the full three-repair path
requires a stricter budget choice *before* dispatch; do not treat 300 as a
guaranteed invoice ceiling. A clean run is 168 AIC. Every stage has zero
automatic retries. The original Issue #10 execution approval is still absent.

Keep Draft PR #14 unmerged until independent human review and founder
authorization. A separate founder-authored exact merged-main-SHA comment on
Issue #10 is required before a single bounded paid pilot run. No execution
approval is implied by passing tests or this document.

Dot consumes future engineering status; it never dispatches workers.
