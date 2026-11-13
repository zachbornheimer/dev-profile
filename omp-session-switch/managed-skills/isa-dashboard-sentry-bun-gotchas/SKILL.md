---
name: isa-dashboard-sentry-bun-gotchas
description: "Working in isa-dashboard (SAH) on Sentry, bun, deploy vars, or PRs from this Mac: current repo state, and shell/tool gotchas that cost time (hanging gh/wt, run_command watcher misroute, hook rules)."
---

## Repo state (verified 2026-11-09)
- Bun migration + @sentry/nextjs + api-keys error boundaries already on origin/main (#173, SAH-11903). Local `main` checkout may lag origin; branch from `origin/main`.
- Sentry is dormant in prod: repo has NO `SENTRY_DSN` Actions variable and NO `SENTRY_AUTH_TOKEN` secret (checked via gh api). deploy.yml passes `vars.SENTRY_DSN` -> build arg `NEXT_PUBLIC_SENTRY_DSN`. Org `software-automation-holdings-l`, project slug `isa-dashboard` (existence in Sentry unverified; no token).
- Org-level GH secrets already include LINEAR_API_KEY / LINEAR_CLIENT_ID / LINEAR_WEBHOOK_SECRET.
- `bunx @sentry/agent-plugin install -y --no-telemetry 'software-automation-holdings-l#612a04fa84'` only detects Cursor on this machine; the project-creation step must then run inside an agent session with the plugin's Sentry MCP (OAuth). omp is not a supported target.
- `omp/sentry` tool needs SENTRY_AUTH_TOKEN in the omp process env; it is not callable via tool_call and not mounted at xd://sentry from a session that lacks it.

## Shell gotchas
- `gh` (variable/secret list, `gh pr create`) and `wt switch` can hang for minutes when the machine is loaded. Use `gh api ... --jq` through eval `sh(..., timeout=...)`, the `github` tool for `pr_create`, and `wt switch --no-hooks --no-cd --yes --create <branch> --base origin/main` run as a background job + `wait`.
- `run_command` can misroute a plain `curl` to a herdr "watcher" pane that never returns; use eval (Python urllib / sh) instead.
- Rules block: recursive grep/`git grep -r` in shell (use the grep tool on a `git archive` export in /tmp), npm/npx (use bunx), and `--no-verify` on commit/push (hooks take ~2 min incl. 678 tests; run them in background).
- Don't poll `proc://<id>`; arm one `wait` and re-wait on timed_out.
