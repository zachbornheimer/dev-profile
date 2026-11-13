---
name: mini-media-stack-gotchas
description: "Use when diagnosing stalled media acquisition, failing homelabctl apply, or odd ssh/mise/git failures on the homelab Mac mini (sonarr/radarr/lidarr/qbittorrent/prowlarr)."
---

# Mini media stack gotchas (measured 2026-11-10)

## Reaching the mini
- Use `ssh mini-lan` when Tailscale SSH needs a browser re-auth (12h `check` ACL). Non-interactive PATH lacks Homebrew: prefix `export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin; export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock;`.
- The mini has no `rg` or `timeout`. Its `mise` (2026.7.5) cannot parse the dotfile-synced `~/.config/mise/config.toml`, so `mise run ...` and git hooks fail there; run `./state/bin/homelabctl ...` directly and conclude merges with `git -c core.hooksPath=/dev/null commit --no-edit`.
- A dotfile sync overwrote `~/.ssh/config` with the laptop copy (dropped NAS and `github.com-homelab` stanzas). Mini-only stanzas live in `~/.ssh/homelab-mini.conf`, included first. Repo has `core.sshCommand` + ssh.github.com:443 remote set locally.
- `brew upgrade` hangs on Spotlight `mdfind`; do not run brew on the mini.

## Disk full -> everything breaks
- /System/Volumes/Data at 100% (mise cache 38 GB) made Colima VM EIO: every `docker exec` failed. Free regenerable cache (`mise cache clear`), then the VM recovers without a cycle. Check `df` first when docker exec returns input/output error.

## homelabctl apply hangs
- `tmutil isexcluded` blocks (STAT U) when Time Machine destination is offline (backupd `FindingBackupVol`); fixed by 20s deadline in PR #389. Use `sudo -n tmutil stopbackup` and kill the stuck child if an older binary is installed.

## Why acquisition stalls
- Sonarr anime profile minFormatScore must be 0; Japanese-original series must be seriesType anime. Radarr profiles need language Original and Bluray size floors (20/8 MB/min) or Ghibli-type films are rejected. All now declared + healed (PR #387).
- Lidarr: wanted albums need profile that allows Unknown quality (`Recovery`, id 5, clone of Any). Prowlarr floors: TPB/Knaben minimum_seeders 1 (PR #390). Roughly half of lost albums have no release on enabled indexers; MyAnonamouse returns 403 (needs owner login).
- Lidarr free-space gate must measure `docker exec lidarr df -Pk /media/music`; its API reports /volume1.
- Lost-music loop: `config/lidarr/lost-albums.tsv` + versioned CSV; cron requests 40 albums/run; `homelabctl check` shows the ledger.
- Long Python/API scripts over ssh time out at 290s: run in background and read a log.
