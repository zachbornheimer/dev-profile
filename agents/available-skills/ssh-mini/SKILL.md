---
name: ssh-mini
description: SSH to Zach's Mac mini (homelab Docker/colima host). Use when running docker on the mini, checking jellyfin/radarr/qbit/homelab compose, or any "mini" remote command. Prefer ssh-mini over raw ssh; on a headless or ephemeral machine use the mini-lan alias.
---

# ssh-mini — Mac mini / homelab host access

## Use this whenever

- Homelab **Docker** status (`docker ps`, compose up/down/logs)
- Anything on the **Mac mini** (not NAS, not this MacBook)
- User says mini / tdarr-mini / mac-mini / colima-on-mini

## Do this (not raw multi-key ssh)

```bash
# Interactive
ssh-mini
# or
ssh mini

# Remote command (PATH includes Homebrew → docker works)
ssh-mini docker ps -a
ssh-mini 'cd ~/homelab && docker compose ps'
```

Wrapper lives at `~/.local/bin/ssh-mini` (also `mini`). It always uses `/usr/bin/ssh` + Host `mini` + `IdentitiesOnly` + `~/.ssh/claude_macmini`.

On a headless or ephemeral machine (relay sandbox, VPS) the wrapper is not installed and `ssh mini` hangs: see **Headless or ephemeral machine** below.

## Facts agents get wrong

| Wrong                                                    | Right                                                                                                                                                  |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `192.168.1.102`                                          | **`192.168.4.102`** (VLAN). 1.102 is stale/offline.                                                                                                    |
| User `zbornheimer`                                       | **`zachbornheimer`**                                                                                                                                   |
| Agent’s default `ssh` (30 keys)                          | **IdentitiesOnly** + `claude_macmini` only — else “Too many authentication failures”                                                                   |
| Bare `docker` on remote non-login shell                  | **PATH** needs `/opt/homebrew/bin` — `ssh-mini` injects it                                                                                             |
| Colima IP `192.168.4.118` as SSH target                  | That is the **VM**, not the host. SSH the mini host; Docker talks to colima’s socket on the mini.                                                      |
| This MacBook’s colima                                    | Local only (agentmux, etc.). Homelab stack is on the **mini**.                                                                                         |
| `ssh -f` / `ssh … &` without a timeout                   | Never. Prefer `ssh host -- cmd` (or `ssh-mini cmd`) so the session **exits** when the command does. Backgrounded ssh survives `tool_result` (ZYS-732). |
| Tool-started `ControlMaster` / `ControlPath` multiplexer | Don't. It outlives the command. One-shot `ssh host -- cmd` only.                                                                                       |
| `ssh mini` or `read ssh://mini/...` from a headless box  | Stops at Tailscale's interactive check and hangs. Use `mini-lan`.                                                                                      |

## Do not leave ssh running

A tool-started ssh shell must not survive after `tool_result` returns.

- Never `ssh -f` and never background ssh without a timeout wrapping the whole invocation (`timeout 30 ssh host -- cmd`).
- Prefer `ssh host -- cmd` so the remote session ends with the command.
- Session-scoped cleanup: `~/.agents/hooks/ssh-session-reap.py` pkills leftover ssh tagged with this session on PostToolUse/Stop. It will not touch untagged terminals, `-N` tunnels, or other sessions.

## SSH config aliases

`~/.ssh/config` has two routes to the mini:

```text
# Keyless Tailscale SSH (laptop, interactive machines).
Host mini mac-mini zacharys-mini
  HostName zacharys-mac-mini.tail158749.ts.net
  User zachbornheimer
  PreferredAuthentications none

# Plain OpenSSH with the claude_macmini key (no Tailscale check).
Host mini-lan
  HostName 192.168.4.102
  User zachbornheimer
  IdentityFile ~/.ssh/claude_macmini
  IdentitiesOnly yes
```

## Headless or ephemeral machine

`ssh mini` and the `ssh://mini/...` read path stop at Tailscale's interactive check (`To authenticate, visit: https://login.tailscale.com/a/...`). Nobody can complete it headless, so the command hangs until `timeout` kills it (exit 124).

Use `mini-lan`. Verified from the relay sandbox on 2026-11-12: key auth, no browser check.

```bash
timeout 90 ssh -o BatchMode=yes -o ConnectTimeout=10 mini-lan \
  'export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"; cd ~/homelab && docker ps'
```

- A non-login remote shell has no Homebrew on PATH. Export it in the command, as above, before `docker`.
- The mini prints `.zshenv ... .cargo/env: no such file` on stdout. It is harmless; filter it with `grep -v cargo`.
- `cmd | tail; echo EXIT=$?` reports `tail`'s status, not `cmd`'s. Capture the status before the pipe if it matters.

## Quick health check

```bash
ssh-mini 'hostname; docker ps --format "table {{.Names}}\t{{.Status}}"'
```

If that fails: ping `192.168.4.102`, confirm VNC/user is on the mini, confirm `~/.ssh/claude_macmini` still authorized.

## Related

- Homelab compose: `~/homelab` **on the mini** (and often mirrored under `~/Developer/Personal/homelab` on the laptop for git).
- NAS is separate: `ssh nas` / `gorillabank` (`ravn@192.168.1.99`) — not this skill.
- Home Assistant skill: `home-assistant-homelab` (HA config), still use `ssh-mini` for live container checks.
