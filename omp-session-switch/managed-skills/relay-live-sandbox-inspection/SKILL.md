---
name: relay-live-sandbox-inspection
description: "When diagnosing a live or just-finished Relay (relay-edge) run: reading its E2B sandbox, its Workflow steps, and the ticket's agent activities from the Mac"
---

# Inspecting a live Relay run

## Workflow steps (Cloudflare)
- `GET /accounts/{acct}/workflows/relay-run/instances?per_page=10` lists turns newest first. Turn ids share the
  first 8 characters of the agent session id; a continuation turn's id is derived from the previous one.
- `GET .../instances/{id}` gives `steps[]` with `name` suffixed `-1` (e.g. `verdict-1`, `release-1`) and a
  **truncated string** `output`. Do not `JSON.parse` it; slice or regex it. `verdict-1.output` holds the
  decision (`kind`, `next`), `release-1.output` the next turn's instruction.
- Auth: wrangler OAuth token from `~/Library/Preferences/.wrangler/config/default.toml` (`oauth_token`).

## Agent activities (Linear)
- `agentSession(id){ activities(last:N) }` returned the OLDEST items here. Fetch `first:250`, sort by
  `createdAt`, take the tail.

## The sandbox itself (E2B)
- List: `GET https://api.e2b.app/v2/sandboxes?state=running` with `X-API-Key` (op://Zysys/E2B API Key/credential).
  The v1 `/sandboxes` route returned an empty list while a sandbox ran. `metadata.ticket` names the ticket.
- Importing the `e2b` SDK inside the omp eval kernel fails (`Cannot find package 'openapi-fetch'`). Run a
  tiny script with bun from its own directory instead: `/tmp/e2bsdk/peek.mjs <sandboxId> <command>` after
  `bun add e2b` there (`Sandbox.connect(id, {apiKey})`, `commands.run(cmd)`).
- Useful reads: `grep E2B-SESSION /tmp/session.out` (prep markers), `/tmp/session.rc`, the mise history repo
  at `~/.local/state/mise/history/repo.git` (its remote ref is `origin/setup`, there is no `origin/history`).

## Known traps found 2026-11-10
- `git rev-parse <missing-ref>` without `--verify` prints the ref name to stdout; `a || b` then captures two
  lines. Always `rev-parse -q --verify` in shell fallbacks.
- A Relay app token can create issues, comments and state changes in ZYS but cannot create workflow states
  (`not allowed to take action`). ZYS has no Hold state; Relay's Hold lands on `Initial Ticket Review`.
