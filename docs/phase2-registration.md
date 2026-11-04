# Phase 2 registration repair — no execution

At 2026-11-04 17:35:46 UTC, GET /repos/rpickett578/gh-aw-codex-pilot/actions/workflows/phase2-chain.yml
returned HTTP 404 (request C2C8:1A18E2:F44BB:32A31B:6AEB6CF2). The inventory listed
only Synthetic CI (407045843) and inert Synthetic Fix (407067426), both active.
The chain file exists on default branch main at fe6bf5b4a385da3957b0f5b1678b163510da47cf.
No check suites, check runs or workflow validation annotations exist on that merge.
Actions are enabled; the missing workflow is not listed as disabled.

GitHub's official [incident](https://www.githubstatus.com/incidents/xr3myzj7ms51)
reported delayed triggering events and status updates, and was resolved at
17:01:11 UTC. The installation merged at 17:28:43 UTC, after that resolution.
The incident alone does not establish why this workflow remains unregistered.

Independent actionlint v1.7.12 validation found three undeclared input references:
review used head_sha/review_id without declaring either, and repair used head_sha
without declaring it. Remove only those unused environment entries and regenerate
the two official locks with the same gh-aw v1.0.1 and action pin. The root DAG,
admission code, next workflow, model/effort, tokens, budgets and safety policies
remain unchanged. This corrects lint defects; it does not prove the 404's cause.

The latest released actionlint has not modeled queue:max and job.workflow_* yet.
Both are supported by current GitHub.com documentation:
[concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency),
[job context](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#job-context).
Validation suppresses only those two precise diagnostic classes. Other syntax,
undefined inputs, reusable linkage and expression errors remain fatal. Shellcheck
and pyflakes are explicitly not run; this is Actions-aware structural validation.
The handwritten chain passes without suppressions; the three generated locks pass
with these documented compatibility exclusions. CI downloads checksum-pinned
actionlint v1.7.12 and repeats all four validations plus the existing 17 gate tests.

The required synthetic-tests name and ordinary source-only functional CI paths
remain intact. A separate exact-base/branch/regular-file/hash installation path
admits only this reviewed repair's fixed file set. It rejects implementation,
fixture, task, admission-code, test, next-workflow or root-DAG changes.

After human-reviewed merge, recheck the exact workflow endpoint and inventory.
Do not dispatch to probe registration. If it remains absent, the official
[gh-aw inert registration procedure](https://github.github.com/gh-aw/setup/cli/#run-from-a-feature-branch)
documents a separately reviewed non-executing file at the same workflow path:
manual trigger only, permissions:{}, no secrets, one job with if:false. It is not
an API refresh or a guarantee of recovery; applying it would replace the active
main entry point and require subsequent reviewed restoration. This PR does not
perform that extra change or change default branches. If needed, prefer GitHub
support with the request ID and validated files before another installation.

No merge, dispatch, authorization-variable activation, credential change or paid
AI operation is part of this repair. PHASE2_EXECUTION_SHA remains absent.
