---
name: vps-up-off-and-untagged
description: "Diagnose vps:up stuck on \"waiting for boot (status: off)\" and an untagged fleet Tailscale node."
---

# vps:up stuck off, or the fleet node is untagged

Use when `mise run vps:up` logs `reusing existing agent-fleet-backend` and then `waiting for boot (status: off)`, or when a joined node has `Tags: null`.

## Status off is not a boot wait

The idle reaper runs `systemctl poweroff`. Hetzner then shows `status=off` and only `create_server` / `start_server` in `/servers/<id>/actions`. Reuse does not boot the guest. Polling never reaches `tailscale up`.

`wait_for_server` in `tools/vps/vps-up.sh` must `POST /servers/<id>/actions/poweron` once, then poll. Landed on main as `2c80aff` (2026-11-08). A regression looks exactly like the original hang: many `waiting for boot (status: off)` lines and no `powering on` line. Do not delete the box to "fix" it.

## The Zysys key does not auto-tag

`vps_resolve_tskey` reads 1Password item `Tailscale Fleet (AI) Ephemeral API Key`, vault `Zysys`, field `credential`. It resolves as `tskey-auth-`. That is the key `tailscale up` gets, on stdin, with `--force-reauth` after `tailscale logout`.

It does not stamp tags. After a successful join on 2026-11-08, `agent-fleet-backend` (`100.98.92.112`, DNS `agent-fleet-backend-1.tail158749.ts.net`, created 2026-10-31) had `Tags: null`. The item has no tag field. A tagged auth key has to be minted with the tag in the Tailscale admin console and stored back in that item. Do not treat a successful `tailscale up` as proof of tags. Check `tailscale status --json` `.Self.Tags` on the box.

## Capabilities install dies on the Mac gh path

Adopted dotfiles leave `credential.https://github.com.helper` pointing at the macOS binary (`gh_2.103.3_macOS_arm64`). `provision_env` skips `gh auth setup-git` when the string `gh auth git-credential` is already present, so the Mac path stays. The clone then fails with `gh: not found`. A live repair (`git config --global --unset` of the missing binary, then `gh auth setup-git`) lasts until the next `vps:up` copies the Mac config back.
