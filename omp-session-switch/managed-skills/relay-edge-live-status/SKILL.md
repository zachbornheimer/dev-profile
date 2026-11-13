---
name: relay-edge-live-status
description: "Check whether the dev-env relay-edge Worker (Linear ticket → E2B sandbox → omp) is actually completing tickets, using wrangler workflow instances, /admin/status and the sandbox tail. Use when asked about the state of Relay, mobile ticket assignment, or whether a ticket run worked."
---

# relay-edge live status

Code: `~/Developer/Personal/dev-env/cloudflare/relay-edge` (worker.mjs, run.mjs, brief.mjs, gate.mjs, tail.mjs, deploy.sh). The sandbox setup is `tools/container/relay-machine.sh` + `e2b-session-container.sh`. Live at `relay.zachandaj.com`. Run commands through `run_command`.

## Rule: a "Completed" workflow is not a finished ticket
`wrangler workflows instances list relay-run` shows `✅ Completed` even when the sandbox died during bootstrap with an empty reply (the `finish` step succeeds either way). Judge a run by its `poll-N` output and the `reply`, never by the status column.

## Steps (all read-only)
1. Health and counters: `curl -sS https://relay.zachandaj.com/healthz`. For counters, send `Authorization: Bearer $(sed -n 's/^RELAY_EDGE_TOKEN=//p' ~/.config/relay/env | tail -1)` to `/admin/status`. It returns `{deliveries,lastDeliveryMs,activeTurns,timeoutMinutes}`.
2. Run history: `cd cloudflare/relay-edge && timeout 60 bunx wrangler workflows instances list relay-run`. Newest first, with created, modified and status.
3. One run: `bunx wrangler workflows instances describe relay-run <id> --truncate-output-limit 30000 > /tmp/x.txt`. Each `poll-N-1` step's Output holds `state.plain`, the sandbox stdout so far, plus `offset`, `store.path`, `reply`, `prepFailure`. Without the flag, output is cut at about 1000 chars and hides the failure line.
4. Is omp running? `store.path` empty and `offset` small means still bootstrapping. A non-empty `store.path` with a growing `offset` means omp is writing its transcript to the Neon store.
5. Live sandboxes: `mise run e2b:status` from dev-env (it prints "no dev-env container sandboxes" when none are live).
6. Code vs secret deploys: `bunx wrangler deployments list` lists secret changes as deployments. Filter on `Source: Upload` to find the last code deploy.

## Gotchas
- `bun tail.mjs` needs `E2B_API_KEY` (`op read 'op://Zysys/E2B API Key/credential'`). Through `run_command` it hung past 20s with no output, probably on `op read`. Wrap it in `timeout 30` and `pkill -f 'bun tail.mjs'` if it hangs. Prefer the workflow `poll-N` output.
- Sandbox mise/dotfiles sync is `--sync fetch-only` until `relay-machine.sh` reaches `adopt-dotfile-history.sh share`, which only runs after the ticket gate passes. If runs never get past the gate, nothing syncs back to the Mac.
- Don't conclude from commit counts. Many `fix(relay-edge)` commits in a row mean the bootstrap was failing run after run.
