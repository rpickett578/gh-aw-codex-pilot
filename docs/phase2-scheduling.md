# Skip-aware scheduling correction — no paid dispatch

Actual run [41891536813](https://github.com/rpickett578/gh-aw-codex-pilot/actions/runs/41891536813)
at 40ebfd180e4285167d62e9d0ce680b73af5a1116 reported root success but route/continue
success, repair skipped and next skipped. The next reusable caller relied on the
implicit success condition. [GitHub's dependency rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs)
propagate skipped ancestors unless an explicit condition permits continuation.

The correction is an explicit !cancelled() status condition plus successful route
and continue results. No worker inputs, model/effort, source allowlists, budgets,
credentials, native safe outputs or zero-retry rules change.

## Real scheduling proof

PR CI reproduces the core native route -> optional repair -> continue -> next
graph. Route outputs repair=false; repair is skipped; continue has the live graph's
same skip-aware condition; next calls a real reusable workflow with the corrected
caller condition. The callee only writes a fixed output marker. Fixture jobs have
permissions:{}, no secrets/token references, no checkout, API calls or AI execution.
A proof job requires actual route/continue/next success, repair skipped and the
callee output. The existing synthetic-tests required check runs with always()
and fails if that proof fails/skips, avoiding another skipped-required-check gap.

The Draft PR's actual GitHub job results, not local simulations or lint, are the
scheduling evidence. This fixture creates no PR and is not a paid pilot claim.

## Fail-closed real-pilot acceptance

A final always() read-only job requires successful admit, review, route, continue
and next, and repair success only when genuinely required (otherwise skipped).
It rejects cancellation and missing native PR outputs, then verifies the actual
open unmerged Draft PR on the fixed pilot-only next-task branch, one approved
source file, and the exact current-run native create_pull_request manifest entry.
It also requires actual GitHub CI success on that PR's exact head via the existing
bounded metadata wait. Missing PR, skipped continuation, failed/pending CI beyond
the bound or wrong publication makes the root fail. No check status is fabricated.

## One prepared replacement

Both run 41880752255 (original failure) and 41891536813 (recovery-v1 root success
but skipped next) remain permanently consumed. Recovery-v2 admission requires
those exact IDs, keys, SHAs, terminal conclusions and attempt 1, plus only its own
current run at the separately authorized installation SHA. Unknown history,
replays and a second v2 attempt fail before inference. There is no generic counter
or retry mechanism. Original concurrency and static reverse-ascii-v1 task remain.

Do not dispatch during this repair. First obtain actual hosted scheduling proof,
then legitimate human review/merge and separate paid recovery-v2 authorization.
After fresh preflight and substituting the verified reviewed merged SHA, the sole
future activation is:

```powershell
$approvedSha = 'VERIFIED_REVIEWED_MERGED_MAIN_SHA'
$key = 'phase2-2-f50e1a8ccc84cee5812c31938a31c93a078e7103-reverse-ascii-v1-recovery-v2'
gh variable set PHASE2_EXECUTION_SHA --repo rpickett578/gh-aw-codex-pilot --body $approvedSha
gh workflow run phase2-chain.yml --repo rpickett578/gh-aw-codex-pilot --ref main -f "recovery_key=$key"
```

Never rerun failed/skipped jobs. Remove PHASE2_EXECUTION_SHA after terminal status
and independently verify absence. Leave every AI-generated PR unmerged.
