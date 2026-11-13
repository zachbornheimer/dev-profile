---
name: relay-edge-run-diagnosis
description: "Check whether Linear tickets assigned to Relay actually ran work in dev-env's cloudflare/relay-edge Worker + E2B sandbox, and probe E2B sandboxes for setup experiments"
---

Use when asked "does Relay / mobile ticket assignment actually work", or when debugging cloudflare/relay-edge runs in ~/Developer/Personal/dev-env.

Key fact: a Cloudflare Workflow status of "Completed" does NOT mean the ticket was worked. Runs that died in sandbox bootstrap still show Completed (finish step posts the failure). Judge by the run's poll output: did omp start, is `reply` non-empty, did the exit gate pass.

Procedure (run from cloudflare/relay-edge, all via run_command):
1. Health/queue: `curl -H "Authorization: Bearer $(sed -n 's/^RELAY_EDGE_TOKEN=//p' ~/.config/relay/env | tail -1)" https://relay.zachandaj.com/admin/status` (deliveries, activeTurns); `/healthz` needs no auth.
2. Run list: `bunx wrangler workflows instances list relay-run` (newest first; durations of ~4-6 min repeated = bootstrap failing, a real session is 15-40 min).
3. One run: `bunx wrangler workflows instances describe relay-run <id> --truncate-output-limit 30000 > /tmp/x.txt`; read the last `poll-N-1` step Output (state.plain/tail = sandbox stdout, `prep:`/`prep_failed:` markers, state.reply). Output with raw `\n`: sed 's/\\\\n/\n/g'.
4. Code deploys: `bunx wrangler deployments list` (Source: Upload vs Secret Change; secret changes alone do not deploy new code).
5. Live sandbox tail: `tail.mjs` needs E2B_API_KEY from `op read 'op://Zysys/E2B API Key/credential'`; it can hang >20s and get promoted to a background job whose output is unreadable here — prefer `mise run e2b:status` and the workflow poll output.
6. Dotfile sync back to the Mac is `--sync fetch-only` until relay-machine.sh's `share` step passes; treat publish-from-sandbox as unproven unless a run shows `dot sync mode=` with share on.

E2B probe sandbox for setup experiments (nix etc.): `mise run e2b:up --name <n> --phase probe --phase apt`; run commands with `uv run tools/container/e2b.py run --name <n> --timeout N [--env-file 0600file] '<cmd>'`; tear down with `mise run e2b:down --name <n>`. Sandbox: x86_64, 2 vCPU/4 GB, ~28 GB disk, non-root with sudo, ~55 min life. Nix installs in ~7 s (`install.determinate.systems/nix | sudo sh -s -- install linux --init none --no-confirm`); start `nix-daemon` by hand. Building the omp fork from source via the flake used ~22 GB of 28 GB before compiling (no binary cache). run_command refuses `sleep` alongside other commands and promotes >20s commands to unreadable background jobs, so poll with short `tail --pid` / timeout calls.
