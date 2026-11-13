---
name: op-cli-hang-agent-shell
description: "Use when a 1Password op command (whoami, item get) hangs or returns nothing in an agent shell, or when a subagent needs a Tailscale auth key from 1Password for a permanent server."
---

# `op` hangs in the agent shell (observed 2026-11-09)

## Symptoms
- `op whoami` / `op item get ...` print nothing and never return. `timeout 15 op ...` does not stop it (SIGTERM ignored); needs `timeout -k 2 12 op ...`.
- Hangs on BOTH paths: with `OP_SERVICE_ACCOUNT_TOKEN` set (it is set in the agent env) and with `env -u OP_SERVICE_ACCOUNT_TOKEN` (desktop-app integration). The 1Password app and `op daemon` were running.
- Likely cause: app locked or an unanswered integration/Touch ID prompt; or a stale service-account token. Unverified.

## What to do
1. Do not retry in a loop or let a subagent burn minutes on it. One probe: `env -u OP_SERVICE_ACCOUNT_TOKEN timeout -k 2 12 op whoami`; exit 137 = still hung.
2. Ask the user to unlock 1Password / dismiss the prompt and run `op whoami` in their own terminal. Then retry.
3. Never print the token or key; redact `tskey-`/`ops_` in any output.

## Command pitfalls
- NEVER `pkill -f 'op whoami'` inside the same `run_command`: `-f` matches the shell's own command line and kills it, producing empty output that looks like a hang. Use a pid or `pkill -x op`.
- Background-promoted jobs (>20s) report output via the log file path in the wake record; read that file.

## Tailscale auth key choice for permanent servers
- `vps-up.sh` uses item 'Tailscale Fleet (AI) Ephemeral API Key' (vault Zysys, field `credential`): ephemeral, for throwaway VPSes. Do NOT use it for a permanent server (node vanishes when offline).
- 'Tailscale API Credentials' (vault Personal) may be an API token, not a `tskey-auth-` key; inspect field labels without printing values before use.
- A permanent server needs a reusable, non-ephemeral, preferably tagged auth key (Tailscale admin Settings > Keys).
- Pass the key to the remote `tailscale up --auth-key` via stdin/env, never argv or disk.

## zysys srv1 facts
- Reach only via jump: `ssh -J mini -o IdentitiesOnly=yes -i ~/.ssh/1p/zysys-hosting-key.pub ec2-user@srv1.web.zysyshosting.com`. Direct SSH from the laptop times out.
- AlmaLinux 9.8, passwordless sudo, tailscale not installed (as of 2026-11-09). Tailscale dnf repo: https://pkgs.tailscale.com/stable/centos/9/tailscale.repo. Keep `-J mini` path intact; no `--ssh`, no sshd/firewall changes unless asked.
- Second zysys server is the DB server; hostname not yet given by the user.
