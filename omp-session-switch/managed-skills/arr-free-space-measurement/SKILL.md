---
name: arr-free-space-measurement
description: "Use when a Sonarr/Radarr/Lidarr free-space gate, queue gate, or \"not enough disk\" refusal fires on the homelab, or when the arrs are not grabbing/acquisitions look stalled — the arrs' own freeSpace/diskspace numbers lie on this NAS."
---

# *arr free-space gates lie on the homelab NAS; measure the drive

## The layout that causes it

NAS (192.168.1.99) mounts:

| Path | Drive | Capacity |
|---|---|---|
| `/volume1` | WD (DSM volume) | 5.3T total, ~277G free |
| `/volumeUSB1/usbshare` | WesternDigital USB | 3.6T, ~1.3T free |
| `/volumeUSB2/usbshare` | Seagate USB | 3.6T, ~763G free |

`/volume1/media/{music,downloads,movies,tv}` are **bind mounts** onto the USB drives, exported over NFS. So `/media/music` inside a container is the Seagate, but any statfs that resolves the *exported* parent reports `/volume1`'s 277 GiB.

## The lie, proven 2026-11-09

For `/media/music`:

- `rootFolder.freeSpace` (Lidarr) → 276 GiB (`/volume1`)
- `GET /api/v1/diskspace` → 762 GiB once, then 276 GiB a minute later, then the mount disappeared from the list
- `docker exec lidarr df -Pk /media/music` → 799281536 KiB ≈ 762 GiB, stable (Seagate)

Consequence: `scripts/lidarr_request_albums.py upgrade` refused every run with `free space 277 GiB < --min-free-gib 300`, so no lossless replacement was ever searched while 763 GiB was free.

## Rule

Do not gate *arr work on `rootFolder.freeSpace` or `/api/v1/diskspace`. Measure the filesystem itself where it is mounted:

```sh
docker exec <container> df -Pk <path>   # column 4 = Available in KiB
```

`scripts/lidarr_request_albums.py:root_free` now does exactly this (PR #385), falling back to diskspace and then to `rootFolder.freeSpace` only when the measurement cannot be taken. Reuse that shape for any new sonarr/radarr free-space gate instead of copying the cached-value pattern.

## Working recipe for the mini

```sh
ssh mini-lan 'export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin; \
  export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock; cd ~/homelab && \
  uv run scripts/lidarr_request_albums.py upgrade --limit 25 --min-age-days 7 --apply'
```

`docker exec` works under the LaunchDaemon environment (Colima is the default docker context); no `DOCKER_HOST` export is needed there. Under an agent shell, set it.

## Adjacent non-gotchas

- A `searched_recently` skip is normal: the script marks each album searched for `--min-age-days`, so a second run in the same day returns `batch: []` with the gate passing. That is success, not a refusal.
- `free_gib` in the summary is the value the gate used. Check it against `df`, not against `/volume1`.
