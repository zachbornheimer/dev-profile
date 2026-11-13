---
name: relay-edge-deploy-verify
description: "Deploy and live-verify the Cloudflare relay-edge Worker/Workflow and VPS/E2B MachinePort adapters (machine.yaml, /admin/machine, vps-runner.service, and flock-serialized guest bootstrap)."
---

# relay-edge-deploy-verify

Deploy a change to the Cloudflare `relay-edge` Worker/Workflow (`cloudflare/relay-edge` in `dev-env`) and prove it live with a real Linear ticket across both `provider: hetzner` and `provider: e2b`.

## Architecture & Machine Policy (`machine.yaml` & `/admin/machine`)

- **Declarative config (`cloudflare/relay-edge/machine.yaml`):**
  ```yaml
  provider: hetzner
  allow_parallel_runs: true
  ```
  (`provider: hetzner | e2b`, `allow_parallel_runs: true | false`).
- **Runtime inspection & override (`GET/POST https://relay.zachandaj.com/admin/machine`):**
  - `GET /admin/machine` (with `Authorization: Bearer $RELAY_EDGE_TOKEN` from `~/.config/relay/env`) returns the active `{ provider, allow_parallel_runs, source }`.
  - `POST /admin/machine` accepts 2-line YAML in the body or `?provider=e2b&allow_parallel_runs=false` to switch live in Durable Object storage without redeploying, or `?reset=1` to revert to `machine.yaml`.
- **`MachinePort` (`cloudflare/relay-edge/machine.mjs`):**
  - `RelayRun` (`run.mjs`) calls only `lease()`, `start()`, `poll()`, and `release()`, with all per-run files isolated under `/tmp/relay-run-<runId>` (`runPaths`).
  - `e2b` adapter creates a fresh E2B sandbox per turn and kills it on `release()`.
  - `hetzner` adapter powers on `agent-fleet-backend` via the Hetzner Cloud API if off, seals payloads with AES-256-GCM (`sealPayload`/`unsealPayload`), and calls `vps-runner.service` (`tools/vps/vps-runner.mjs`, port 8080 over `<ip>.sslip.io` using `HETZNER_RUNNER_TOKEN`).
- **Concurrency scheduler (`cloudflare/relay-edge/slots.mjs`):**
  - Same-ticket turns always serialize on `active:<ticket>`.
  - `allow_parallel_runs: true` runs distinct tickets in parallel in isolated `/tmp/relay-run-<runId>` directories and per-run repo clones (`RELAY_REPO_ROOT`).
  - `allow_parallel_runs: false` queues additional tickets FIFO in `queue:__machine__` and hands the slot to the next queued ticket in `finishRun()`.
- **Guest bootstrap (`tools/container/relay-machine.sh` & `e2b-session-container.sh`):**
  - Serializes `mise` setup/sync across parallel runs via `flock` on `~/.cache/relay-machine.lock` (closing FD 9 on background `mise dot watch` with `9>&-` so the daemon never holds the lock).
  - Provisioned Hetzner hosts (`~/.cache/relay-machine-established` or `/var/lib/dev-env/provisioned`) skip destructive `mise bootstrap --adopt --replace-history` and run a fast `mise dot pull` + `relay_verify_mise_steps` check.

## Pre-Deploy Gate

Run from a `dev-env` worktree twice before committing/merging:

```bash
shfmt -w tools/vps/vps-idle-reaper.sh tools/container/relay-machine.sh tools/container/e2b-session-container.sh tools/vps/vps-up.sh cloudflare/relay-edge/deploy.sh
shellcheck --severity=warning tools/vps/vps-idle-reaper.sh tools/container/relay-machine.sh tools/container/e2b-session-container.sh tools/vps/vps-up.sh cloudflare/relay-edge/deploy.sh
bun test cloudflare/relay-edge/ && bash tests/relay_machine.sh && bash tests/vps_boot_skip.sh && bash tests/vps_dotfile_sources.sh && bash tests/vps_reuse.sh && bash tests/container_e2b_session_exit.sh
```

## Deploy

Run from `~/Developer/Personal/dev-env/cloudflare/relay-edge` on the Mac (requires 1Password, `gh`, and `wrangler` login):

```bash
./deploy.sh
```

- `deploy.sh` pushes all secrets (`WEBHOOK_SECRET`, `LINEAR_CLIENT_ID`, `LINEAR_CLIENT_SECRET`, `E2B_API_KEY`, `GITHUB_TOKEN`, `RELAY_EDGE_TOKEN`, `TAILSCALE_AUTH_KEY`, `AGE_KEY`, `SSH_KEY`, `SSH_PUB`, `GIT_SSH_SIGNING_KEY_B64`, `GIT_SSH_SIGNING_PUB`, `AUTH_GATEWAY_TOKEN`, `HETZNER_TOKEN`, `HETZNER_RUNNER_TOKEN`) and runs `bunx wrangler deploy`.
- If `1Password` interactive `op read` stalls in an agent shell while `wrangler` secrets are already current, deploy the worker code directly with:
  ```bash
  resume_model=$(sed -n 's/^OMP_RESUME_MODEL=//p' ~/.config/dev-env/omp-session.env | tail -1)
  bunx wrangler deploy ${resume_model:+--var "OMP_RESUME_MODEL:$resume_model"}
  ```

## Live Verification

1. Check `/admin/status` and `/admin/machine`:
   ```bash
   ET=$(sed -n 's/^RELAY_EDGE_TOKEN=//p' ~/.config/relay/env | tail -1)
   curl -fsS -H "Authorization: Bearer $ET" https://relay.zachandaj.com/admin/status | jq .
   curl -fsS -H "Authorization: Bearer $ET" https://relay.zachandaj.com/admin/machine | jq .
   ```
2. Trigger a signed Linear `AgentSessionEvent` webhook (using `op read "op://Zysys/Linear Relay Agent/Signing Secret"` to compute `Linear-Signature` HMAC-SHA256) against a safe test ticket, inspect `/tmp/relay-run-<sessionPrefix>-*/session.out` on `backend.ai` (for `hetzner`), and clean up any test lease via `POST /admin/release?ticket=<issueId>` and `POST /admin/machine?reset=1`.
