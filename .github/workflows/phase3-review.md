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
max-ai-credits: 15
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
  PHASE3_CHAIN_RUN_ID: ${{ github.run_id }}
  PHASE3_STAGE: review
  PHASE3_TARGET_PR: ${{ inputs.pr_number }}
  PHASE3_TARGET_HEAD: ${{ inputs.head_sha }}
  PHASE3_TASK_ID: ${{ inputs.task_id }}
pre-agent-steps:
  - name: Independently admit exact Draft PR and actual passing GitHub CI
    env:
      GH_TOKEN: ${{ github.token }}
    run: |
      set -euo pipefail
      for script in phase3_gate.py phase3_snapshot.py phase3_workspace_guard.py; do
        gh api "repos/rpickett578/gh-aw-codex-pilot/contents/scripts/$script?ref=$GITHUB_WORKFLOW_SHA" --jq .content | base64 --decode > "$RUNNER_TEMP/$script"
      done
      PYTHONPATH="$RUNNER_TEMP" python3 "$RUNNER_TEMP/phase3_snapshot.py" > "$RUNNER_TEMP/phase3-review-admission.json"
      python3 -c 'import json,os; x=json.load(open(os.environ["RUNNER_TEMP"]+"/phase3-review-admission.json")); assert x["action"]=="REVIEW" and x["task"]==os.environ["PHASE3_TASK_ID"] and str(x["pr"])==str(os.environ["PHASE3_TARGET_PR"]) and x["head"]==os.environ["PHASE3_TARGET_HEAD"], "review preflight did not match one exact candidate"'
      mkdir -p /tmp/gh-aw
      python3 -c 'import json,os;json.dump({"run_id":os.environ["GITHUB_RUN_ID"],"task":os.environ["PHASE3_TASK_ID"],"pr":os.environ["PHASE3_TARGET_PR"],"head":os.environ["PHASE3_TARGET_HEAD"],"install_sha":os.environ["PHASE3_INSTALL_SHA"]},open("/tmp/gh-aw/phase3-review-context.json","w"))'
      python3 "$RUNNER_TEMP/phase3_workspace_guard.py" capture "$PHASE3_STAGE"
post-steps:
  - name: Read-only host guard and pinned functional tests
    run: |
      set -euo pipefail
      python3 "$RUNNER_TEMP/phase3_workspace_guard.py" check "$PHASE3_STAGE"
      case "$PHASE3_TASK_ID" in
        ascii-vowel-count-v1) testcase=test/ascii-vowel-count.test.mjs ;;
        strip-ascii-controls-v1) testcase=test/strip-ascii-controls.test.mjs ;;
        collapse-ascii-spaces-v1) testcase=test/collapse-ascii-spaces.test.mjs ;;
        *) exit 1 ;;
      esac
      env -i PATH="$PATH" HOME="$RUNNER_TEMP" node --permission --allow-fs-read="$GITHUB_WORKSPACE" --test-isolation=none --test "$testcase"
safe-outputs:
  max-patch-files: 1
  report-failure-as-issue: false
  report-failed-jobs: false
  threat-detection:
    continue-on-error: false
    report-as-issue: false
    max-ai-credits: 8
    engine:
      id: codex
      version: 0.165.0
      model: openai/gpt-6.1-sol
      max-turns: 3
  steps:
    - name: Recheck exact review target and founder gate before native COMMENT publication
      env:
        GH_TOKEN: ${{ github.token }}
        AGENT_JOB_RESULT: ${{ needs.agent.result }}
      run: |
        set -euo pipefail
        test "$AGENT_JOB_RESULT" = success
        for script in phase3_gate.py phase3_snapshot.py; do
          gh api "repos/rpickett578/gh-aw-codex-pilot/contents/scripts/$script?ref=$GITHUB_WORKFLOW_SHA" --jq .content | base64 --decode > "$RUNNER_TEMP/$script"
        done
        PYTHONPATH="$RUNNER_TEMP" python3 "$RUNNER_TEMP/phase3_snapshot.py" > "$RUNNER_TEMP/phase3-review-recheck.json"
        python3 -c 'import json,os; x=json.load(open(os.environ["RUNNER_TEMP"]+"/phase3-review-recheck.json")); assert x["action"]=="REVIEW" and x["task"]==os.environ["PHASE3_TASK_ID"] and str(x["pr"])==str(os.environ["PHASE3_TARGET_PR"]) and x["head"]==os.environ["PHASE3_TARGET_HEAD"], "review publication target changed"'
  submit-pull-request-review:
    target: "${{ inputs.pr_number }}"
    commit-id: ${{ inputs.head_sha }}
    allowed-events:
      - COMMENT
    max: 1
    github-token: ${{ secrets.GH_AW_CI_TRIGGER_TOKEN }}
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
description: Independent COMMENT-only review for one admitted Phase 3 Draft PR
runs-on: ubuntu-24.04
timeout-minutes: 8
on:
  workflow_call:
    inputs:
      pr_number:
        type: string
        required: true
      head_sha:
        type: string
        required: true
      task_id:
        type: string
        required: true
if: github.repository == 'rpickett578/gh-aw-codex-pilot' && github.actor == 'rpickett578' && github.run_attempt == 1 && vars.PHASE3_INSTALL_SHA == github.workflow_sha
checkout:
  ref: ${{ inputs.head_sha }}
  fetch-depth: 0
  fetch:
    - main
---

Independently inspect the synthetic Phase 3 task in /tmp/gh-aw/phase3-review-context.json,
including the exact current Draft PR diff, the matching approved issue, and its
immutable 11-test fixture. Do not inspect or rely on the prior coder's reasoning
or logs; independently reproduce tests and check for correctness.

Never edit any file or branch. No install, delegation, merge, approvals,
REQUEST_CHANGES, extra worker, deployment, another repository or external network.
Submit exactly one native COMMENT review at the pinned PR number and exact
head commit. A clean review is valid. Do not invent defects.

Include precisely one fenced structured JSON block:

```phase3-review
{"install_sha":"EXACT_INSTALL_SHA","task":"EXACT_TASK_ID","head":"EXACT_HEAD_SHA","verdict":"clean","findings":[]}
```

Replace the placeholders using /tmp/gh-aw/phase3-review-context.json.
For an authentic correctness defect, use verdict "findings" and at most 3
reproducible findings. Each finding MUST contain exactly "input", "expected",
"line", and "reason". "input" must be a compact JSON value (not code).
"expected" MUST be {"value": <JSON result>} or {"error":"TypeError"}, never
a raw result. "line" must be a valid line number in the reviewed source.
"reason" must be a concise reproducible correctness explanation. The
trusted host separately computes the expected result from the task contract,
executes the exact reviewed source without credentials and rejects invented,
nonreproducing or contradictory findings. Never report style-only findings.
If this is a second review after a one-commit correction, no second repair
is allowed; report genuine defects without attempting another correction.
No automatic APPROVE, REQUEST_CHANGES, merge, or code writes.
