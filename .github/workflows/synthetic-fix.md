---
description: One manual synthetic bug fix in an isolated test repository
on:
  workflow_dispatch:
if: github.repository == 'rpickett578/gh-aw-codex-pilot' && github.ref == 'refs/heads/codex/pilot-worker' && github.run_attempt == 1
permissions:
  contents: read
checkout:
  ref: d5c947f0000a32656eb50a55fca0270e28f6aafa
  fetch-depth: 0
  fetch: [main]
engine:
  id: codex
  version: "0.165.0"
  harness:
    max-retries: 0
  config: |
    model_reasoning_effort = "medium"
    [features]
    multi_agent = false
model: openai/gpt-6.1-sol
runs-on: ubuntu-24.04
timeout-minutes: 10
max-turns: 20
max-ai-credits: 100
concurrency:
  group: synthetic-fix
  cancel-in-progress: false
network:
  allowed: []
sandbox:
  agent:
    model-fallback: false
tools:
  github: false
  bash: true
safe-outputs:
  report-failure-as-issue: false
  report-failed-jobs: false
  threat-detection:
    continue-on-error: false
    report-as-issue: false
    max-ai-credits: 50
    engine:
      id: codex
      version: "0.165.0"
      model: openai/gpt-6.1-sol
      max-turns: 3
      config: |
        model_reasoning_effort = "medium"
  create-pull-request:
    title-prefix: "[pilot] "
    draft: true
    max: 1
    base-branch: main
    branch-prefix: codex/pilot-
    fallback-as-issue: false
    auto-close-issue: false
    protected-files: blocked
    allowed-files:
      - src/slugify.mjs
    max-patch-files: 1
    max-patch-size: 16
    github-token-for-extra-empty-commit: ${{ secrets.GH_AW_CI_TRIGGER_TOKEN }}
jobs:
  agent:
    timeout-minutes: 20
  detection:
    timeout-minutes: 10
---

Fix the synthetic ASCII slug bug described in TASK.md. Read AGENTS.md first.
Only edit src/slugify.mjs. Do not edit tests, instructions, workflows, dependencies,
or Git configuration. Do not access other repositories, issues, or services.
Do not delegate or launch subagents. Do not install packages.

Run `node --test test/slugify.test.mjs` before and after the change. The initial
tests must fail. Implement the documented behavior, run the tests, and use the
create_pull_request safe output to submit exactly one draft PR. Include the
observed before/after results and a short explanation. Leave merging and review
to a human. If blocked, report the reason and stop; do not broaden scope.
