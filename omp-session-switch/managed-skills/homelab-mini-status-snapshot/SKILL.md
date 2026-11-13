---
name: homelab-mini-status-snapshot
description: "Gotchas when taking a live homelab status snapshot over SSH to the mini: Tailscale SSH re-auth hang, no timeout on mini zsh, qbit env, which logs exist."
---

# Homelab live status snapshot gotchas

- `ssh mini` goes over Tailscale SSH with a 12h `check` re-auth. When it expires, commands hang until ConnectTimeout with "Tailscale SSH requires an additional check". Use `ssh mini-lan` (LAN break-glass, key auth) for snapshots until the ACL is set to `accept`.
- The mini's zsh has no `timeout` (GNU coreutils absent): `timeout 100 homelabctl status` fails with "command not found" and prints nothing. Run `homelabctl status` bare, or `gtimeout` if installed.
- Non-interactive PATH needs `export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin` and `DOCKER_HOST=unix://$HOME/.colima/default/docker.sock`.
- `~/homelab/.env` may not exist on the mini; qBit creds come from `config/launchd-env/arr.env`. qBit API: `http://127.0.0.1:8080`.
- Stale launchd exit codes in `launchctl list | grep zysys` (grep-lifetime 78, status-report, vps-reap-off) are old records, not live drift; use `homelabctl status` for real drift.
- Librarian logs live in `~/homelab/logs/`: `intake-gate.log`, `librarian-bookstage.log`, `arr-stalled-downloads.log`. `librarian-sweep.log` does not exist.
- Lidarr upgrade job refuses when `/volume1` free < 300 GiB (it checks /volume1, not the Seagate btrfs drive).
- Permanent home for this: a read-only `homelabctl status` rollup; this skill is a bridge.
