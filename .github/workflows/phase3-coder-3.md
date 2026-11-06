---
permissions:
  contents: read
  pull-requests: read
  actions: read
  checks: read
engine:
  id: codex
  version: 0.165.0
  harness:
    max-retries: 0
  config: |
    model_reasoning_effort = "medium"
    [features]
    multi_agent = false
model: openai/gpt-6.1-sol
max-turns: 15
max-ai-credits: 30
network:
  allowed: []
sandbox:
  agent:
    model-fallback: false
tools:
  github: false
  bash: true
env:
  PHASE3_INSTALL_SHA: ${{ vars.PHASE3_INSTALL_SHA }}
  PHASE3_STAGE: coder-3
pre-agent-steps:
  - name: Read-only approved queue and exact task admission
    env:
      GH_TOKEN: ${{ github.token }}
    run: |
      set -euo pipefail
      for script in phase3_gate.py phase3_snapshot.py phase3_workspace_guard.py; do
        gh api "repos/rpickett578/gh-aw-codex-pilot/contents/scripts/$script?ref=$GITHUB_WORKFLOW_SHA" --jq .content | base64 --decode > "$RUNNER_TEMP/$script"
      done
      PYTHONPATH="$RUNNER_TEMP" python3 "$RUNNER_TEMP/phase3_snapshot.py" > "$RUNNER_TEMP/phase3-admission.json"
      python3 -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x["action"]=="CODING" and x["task"]==sys.argv[2] and x["issue"]==int(sys.argv[3]), "unapproved task"' "$RUNNER_TEMP/phase3-admission.json" "collapse-ascii-spaces-v1" "13"
      python3 "$RUNNER_TEMP/phase3_workspace_guard.py" capture "$PHASE3_STAGE"
post-steps:
  - name: Host-only source/commit protection and functional tests
    run: |
      set -euo pipefail
      python3 "$RUNNER_TEMP/phase3_workspace_guard.py" check "$PHASE3_STAGE"
      env -i PATH="$PATH" HOME="$RUNNER_TEMP" node --permission --allow-fs-read="$GITHUB_WORKSPACE" --test-isolation=none --test "test/collapse-ascii-spaces.test.mjs"
safe-outputs:
  max-patch-files: 1
  report-failure-as-issue: false
  report-failed-jobs: false
  threat-detection:
    continue-on-error: false
    report-as-issue: false
    max-ai-credits: 10
    engine:
      id: codex
      version: 0.165.0
      model: openai/gpt-6.1-sol
      max-turns: 3
  steps:
    - name: Recheck issue, founder approval, repository and exact task before publication
      env:
        GH_TOKEN: ${{ github.token }}
        AGENT_JOB_RESULT: ${{ needs.agent.result }}
      run: |
        set -euo pipefail
        test "$AGENT_JOB_RESULT" = success
        for script in phase3_gate.py phase3_snapshot.py; do
          gh api "repos/rpickett578/gh-aw-codex-pilot/contents/scripts/$script?ref=$GITHUB_WORKFLOW_SHA" --jq .content | base64 --decode > "$RUNNER_TEMP/$script"
        done
        PYTHONPATH="$RUNNER_TEMP" python3 "$RUNNER_TEMP/phase3_snapshot.py" > "$RUNNER_TEMP/phase3-recheck.json"
        python3 -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x["action"]=="CODING" and x["task"]==sys.argv[2], "publication admission failed"' "$RUNNER_TEMP/phase3-recheck.json" "collapse-ascii-spaces-v1"
  create-pull-request:
    title-prefix: "[phase3 collapse-ascii-spaces-v1] "
    draft: true
    max: 1
    base-branch: main
    branch-prefix: codex/
    preserve-branch-name: true
    recreate-ref: false
    fallback-as-issue: false
    auto-close-issue: false
    protected-files: blocked
    allowed-files:
      - src/collapse-ascii-spaces.mjs
    max-patch-files: 1
    max-patch-size: 16
    github-token: ${{ secrets.GH_AW_CI_TRIGGER_TOKEN }}
    github-token-for-extra-empty-commit: ${{ secrets.GH_AW_CI_TRIGGER_TOKEN }}
jobs:
  safe_outputs:
    permissions:
      contents: read
      actions: read
      checks: read
      issues: write
      pull-requests: write
  agent:
    timeout-minutes: 15
  detection:
    timeout-minutes: 8
description: Approved Phase 3 synthetic task 3; Draft PR only; no merges
runs-on: ubuntu-24.04
timeout-minutes: 8
on:
  workflow_call:
if: github.repository == 'rpickett578/gh-aw-codex-pilot' && github.actor == 'rpickett578' && github.run_attempt == 1 && vars.PHASE3_INSTALL_SHA == github.workflow_sha
checkout:
  ref: ${{ github.workflow_sha }}
  fetch-depth: 0
  fetch:
    - main
---

Synthetic pilot only. Execute precisely task issue #13 (`collapse-ascii-spaces-v1`) and no other task.
Edit ONLY `src/collapse-ascii-spaces.mjs`. Implement `collapseAsciiSpaces(input)`: Replace maximal runs of ASCII U+0020 space with one ASCII space; preserve one leading/trailing space and all other characters, tabs and newlines. Throw TypeError for non-primitive strings.
Do not edit tests, workflow/config, docs, credentials or any other path. Do not
access other repositories, delegate, install packages, call external networks,
deploy, merge, approve or request review. You must not act as a reviewer.

Run `node --test test/collapse-ascii-spaces.test.mjs` before and after the implementation.
Create exactly the local branch `phase3-collapse-ascii-spaces-v1` from pinned checkout HEAD.
Stage only `src/collapse-ascii-spaces.mjs`; make one ordinary non-merge commit. Never amend,
reset, rebase, force, push, alter remotes, or create extra branches. The sole
commit parent must be the pinned checkout. Verify a clean tree with only that
approved source diff. Use native `create_pull_request` once with branch
`phase3-collapse-ascii-spaces-v1` and draft=true. The separate native publisher may publish remote
branch `codex/phase3-collapse-ascii-spaces-v1`. Do not push manually. Leave the Draft PR unmerged.
After native submission, STOP. Do not start the next worker; only the GitHub
admission chain may do so after actual CI and independent review.
