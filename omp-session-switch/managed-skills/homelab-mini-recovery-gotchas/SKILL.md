---
name: homelab-mini-recovery-gotchas
description: "Use when working on the homelab Mac mini over ssh: disk-full/Colima EIO, apply hanging on tmutil, broken mise/git commit/brew, ssh config overwritten by dotfile sync, arr/Prowlarr API probes, why music recovery stays slow."
---

# Homelab mini: measured gotchas (2026-11-10)

Short-term bridge until these are encoded in `homelabctl`; check `homelabctl check`/AGENTS.md first.

## Reaching the mini
- `ssh mini` is Tailscale SSH and re-prompts a browser login every 12h (check mode); a hung `ssh mini` means that. Use `ssh mini-lan` (192.168.4.102, key path) meanwhile.
- Non-interactive shells have no Homebrew/docker on PATH. Prefix: `export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin; export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock;`. Without it `homelabctl check` reports `exec: "docker": not found`.
- The mini's `~/.ssh/config` is overwritten by a dotfile sync from the laptop (2026-11-10 11:08), dropping `Host nas` and `github.com-homelab`. Fix in place: mini-only stanzas live in `~/.ssh/homelab-mini.conf`, included first from `~/.ssh/config` (NAS = `ravn@192.168.1.99` with `~/.ssh/id_rsa`). Repo also sets local `core.sshCommand` with `~/.ssh/homelab_github_deploy`. If NAS checks fail with "no such identity", re-check the Include line.
- `rg`, `timeout` are not on the mini; use grep/perl alarm.

## Things that hang or fail on the mini
- Host data volume 100% full -> Colima VM filesystem goes EIO (`docker exec` fails "input/output error", `colima ssh` dead, gluetun unhealthy). Freeing space (`mise cache clear`, ~38 GB regenerable) recovered it without a Colima cycle. Biggest hogs: ~/Library/Caches/mise, .colima, homelab/config.
- `mise` on the mini is 2026.7.5 and cannot parse the synced `~/.config/mise/config.toml` (brew:tailscale map form): every `mise run ...` and every git hook that calls mise fails. Do NOT `brew upgrade mise` there: brew hangs on Spotlight `mdfind`. Use `~/homelab/state/bin/homelabctl` directly; rebuild with `bash scripts/homelabctl-install.sh`.
- Merging origin/main on the mini leaves MERGE_HEAD uncommitted: run `git -c core.hooksPath=/dev/null commit --no-edit` as a separate command, then check `.git/MERGE_HEAD` is gone. Branch there is `relay-deploy`.
- `tmutil isexcluded` blocks forever (state U) when Time Machine's SMB destination is offline (backupd `FindingBackupVol`). Fixed in homelab PR #389 (20s deadline, skip with warning). On a binary older than that, `sudo -n tmutil stopbackup` + killing the child unsticks apply.
- `homelabctl apply` exiting 1 as `[blocked · warned]` is the known degraded state (ExternalSSD absent, root-owned LaunchDaemons needing sudo), not a failure of the heals; read the `[changed]` lines.
- Commit hooks (hk) require conventional subject <= 60 chars.

## Probing arr apps
- Run python on the mini over ssh stdin; API keys come from `docker exec <app> cat /config/config.xml`; call via `docker exec <app> sh -c 'curl -s -H "X-Api-Key: .." http://127.0.0.1:<port>/api/<v1|v3>/...'`. Ports: sonarr 8989, radarr 7878, lidarr 8686, prowlarr 9696. Sonarr needs `seriesType: anime` for absolute-numbered releases and the anime profile minFormatScore 0 (declared in homelabctl arr quality config).
- Lidarr `album?includeAllArtistAlbums=false` entries may lack `statistics`; use `.get`.

## Music recovery reality
- Lost library = `config/lidarr/lost-albums.tsv` (805 albums from the 2026-07 Navidrome missing-files CSV, now versioned in repo). Cron requests 40/run. A 12-album sample: 6 albums have no release on any enabled indexer, 4 have seeded releases (1-2 seeders via TPB/Knaben), Lidarr accepted 0/13 (Unknown quality 5, unparsable 4, zero seeders 3). Lowering seeder floor to 1 changed nothing. Remaining levers: MyAnonamouse credentials (Prowlarr MAM session 403), allowing Unknown quality on a recovery profile, a Soulseek source (no slskd container). Pending decisions were pinned.
