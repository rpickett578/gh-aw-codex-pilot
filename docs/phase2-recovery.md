# Recovery-v1 for the observed Phase 2 failure

No paid execution is authorized by this repair. Original run
[41880752255](https://github.com/rpickett578/gh-aw-codex-pilot/actions/runs/41880752255)
failed at main fa995cbf91f4e7d02916e35f0fd8f9979a8ad298. It published authentic clean
COMMENT review [5773146021](https://github.com/rpickett578/gh-aw-codex-pilot/pull/2#pullrequestreview-5773146021)
on f50e1a8ccc84cee5812c31938a31c93a078e7103 and passed 19 tests. No correction or
next-task execution occurred. The original task key stays permanently consumed.

## Working-tree protection

The pinned compiler restores base .github and AGENTS.md after checking out the
older PR head. The observed tracked differences were ci.yml and AGENTS.md, plus
seven newly restored workflow files. The regression constructs the original
synthetic tree from its real bootstrap history and the observed reviewed source
Git blob, then restores the exact executed main's .github/AGENTS files. It proves
the old git diff check returns 1 and unchanged full snapshots compare equal.

Each worker's last pre-agent hook captures a snapshot **after** trusted restoration.
The host loads both helpers from the exact reviewed workflow SHA. The baseline
is at $RUNNER_TEMP/phase2-workspace-guard/baseline.json, outside the workspace,
/tmp/gh-aw and $RUNNER_TEMP/gh-aw. Those are the pinned sandbox's mounted writable
workspace/evidence and read-only helper trees; the baseline directory is not
mounted into the agent. Capture is write-once, directory 0700/file 0400 on Linux;
no baseline artifact is uploaded. The trusted host post-hook checks run/SHA/root/
stage binding before comparison. It fails on missing/overwritten-context state.

Snapshots include every tracked, untracked and ignored entry: path, kind, file
contents SHA-256/size, permissions, directories and symlink targets; symlinks are
not followed, hard-linked files and unsupported entries fail closed. Timestamps
are not content identity. Bounds are 4096 entries/32 MiB. Only root .git Git
administration is outside the working tree; HEAD and index entries are checked
separately. No .github or AGENTS exception exists. Review allows zero changes.
Repair/next allow only their one existing source file, unchanged mode, regular
file <=16 KiB; all other changes, additions and deletions fail. HEAD may not change;
only the allowed source may be staged. Native safe outputs publish code.

The correction worker had the same overlay false failure; it now uses the same
baseline comparison. The next worker also receives the full-tree guard, protecting
immutable tests/configuration. Host post-tests run with an empty credential
environment and Node read-only filesystem permissions without child isolation.
Publication explicitly requires needs.agent.result==success before any native
safe-output processing. This closes the observed behavior where the old failed
post-check still allowed the COMMENT publication. Existing threat detection stays.

## Review and downstream evidence

Accept only github-actions[bot], numeric account ID 41898282, type Bot, COMMENTED
state, exact original commit, exact current root run ID, PR #2 review URL and
native workflow/caller marker. Additionally require the exact native root run
(manual, attempt 1, expected owner/path/SHA/key), a successful review/safe_outputs
job, publication time within that job, and the exact review ID/event/URL in the
run's native safe-output-items manifest. Bound inventory/download/decompression;
do not extract archives or execute downloaded content. The bearer token is never
forwarded to the signed artifact host or printed. Publisher/route gain only read
permissions needed for this evidence; no new secret or write scope is added.

The old review is accepted as authentic regression evidence, but cannot satisfy a
new recovery run: current-run binding still requires a new independent review.
Clean means repair NOT APPLICABLE. Authentic findings still must reproduce and
be resolved. Downstream audit also tightens the native repair-SHA handoff: an
extra CI-trigger child must have exactly the repair parent and the identical Git
tree, not merely be one arbitrary child. Actual exact-head CI success, fixed task,
branch absence, no fallback, file scopes, zero retries and budgets remain intact.
Local mocked clean-path admission tests exercise route/continue/next/publication;
they are not evidence of genuine hosted automatic continuation.

## One replacement, not a retry

The only new static key is:

`phase2-2-f50e1a8ccc84cee5812c31938a31c93a078e7103-reverse-ascii-v1-recovery-v1`

The root run name is that literal, and its manual input must match. The original
concurrency group remains unchanged, serializing both versions. Admission accepts
only the exact failed run 41880752255 plus the current recovery run at the separately
authorized reviewed SHA; any other history, rerun, second recovery attempt, changed
old failure, unknown version or missing SHA gate fails before paid inference.
Any recovery attempt consumes this key, even if skipped, cancelled or failed.
No dynamic recovery counter, arbitrary task ID or automatic retry exists.

## Exact activation — only after separate execution approval

1. Legitimately review and merge this PR; do not weaken any protection.
2. Verify exact merged SHA/locks/CI, active registration, original PR #2 head and
   CI, unchanged secrets/scopes/protections, exactly the original failed Phase 2
   run, no recovery attempt and no next-task branch. Budget remains at most $3
   clean-path/$4.50 correction-path runtime thresholds, not invoice ceilings.
3. Only after explicit recovery-v1 execution authorization, substitute the verified
   approved merged main SHA, set its gate and dispatch **once**:

```powershell
$approvedSha = 'VERIFIED_REVIEWED_MERGED_MAIN_SHA'
$recoveryKey = 'phase2-2-f50e1a8ccc84cee5812c31938a31c93a078e7103-reverse-ascii-v1-recovery-v1'
gh variable set PHASE2_EXECUTION_SHA --repo rpickett578/gh-aw-codex-pilot --body $approvedSha
gh workflow run phase2-chain.yml --repo rpickett578/gh-aw-codex-pilot --ref main -f "recovery_key=$recoveryKey"
```

Do not run these commands during repair/review. No new credentials or permissions
settings are needed. Leave all AI PRs unmerged. After terminal status, remove and
read back absence of the gate:

```powershell
gh variable delete PHASE2_EXECUTION_SHA --repo rpickett578/gh-aw-codex-pilot
gh variable list --repo rpickett578/gh-aw-codex-pilot --json name
```

Never rerun jobs or the root, including failed metadata/admission attempts.
Report real run/review/PR/CI references and usage. Recovery success and automatic
continuation remain NOT EXECUTED until separately authorized and actually proven.
