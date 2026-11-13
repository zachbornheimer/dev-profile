---
name: nas-btrfs-conversion-watch
description: "Check, diagnose and safely extend swap on the Synology NAS while btrfs-convert runs over USB drives: how to tell real conversion progress from swap thrash, and the swapfile hazards that have already bitten."
---

# NAS btrfs conversion: status, stall diagnosis, swap

Host `nas` (Synology DSM, 1.8 GB RAM). Conversion workspace `/volume1/scratch-conversion`
(host it, not on the USB drives). Window scripts `window.sh` / `window-repair.sh <wd|sg> convert`
run `btrfs-convert.static -p -i -L --uuid copy -O ^free-space-tree /dev/sdr1` (= `-i`: xattrs not
copied; the default xattr copy fails with -95 on this kernel).

Drives: `/dev/sdq1` = WesternDigital (converted, btrfs, mounts `/volumeUSB1/usbshare`),
`/dev/sdr1` = Seagate (the long one). Window state files: `win-wd/state`, `win-sg/state`
(values `WINDOW-OK` / `WINDOW-OK-REPAIR` = success; absence = still running or failed).

## Status in one shot

```bash
ssh nas 'sudo -n blkid /dev/sdq1 /dev/sdr1
for w in win-wd win-sg; do echo -n "$w: "; sudo -n cat /volume1/scratch-conversion/$w/state || echo none; done
ps -eo pid,state,etime,time,rss,args | grep "[b]trfs-convert"
sudo -n swapon -s; free -m | head -2'
```

`sudo -n swapon -s` and `wmstat` are the only swap tools — **there is no `vmstat` on DSM**.

## Tell progress from thrash (do not trust "it is running")

`run-sg-*.log` is **0 bytes for the whole run**: btrfs-convert's `-p` progress is line-buffered
behind `nohup`, so nothing flushes until exit. Never conclude "no progress" from that log.

Real signals, in order of value:

1. `/sys/block/sdr/stat` — field 7 (0-based index 6, "sectors written"). This is the only true
   conversion progress counter. Seagate observed 71,344 sectors (35 MB) after 32 h = stalled.
2. `ps -o time -p <pid>` — CPU time. Frozen CPU time with elapsed advancing = not working.
3. `/proc/<pid>/io` twice: `rchar` frozen while `read_bytes` climbs = the I/O is **swap-in**, not
   conversion reads.
4. `/proc/<pid>/stack` — `wait_on_page_bit_killable` ← `handle_mm_fault` = faulting a swapped-out
   page. Note the wait is **killable**, so SIGTERM/SIGKILL are honoured even in state `D`.
5. `uptime` load: IO 10 with CPU 0.09 = 100% I/O wait.

Memory attribution: `ps -eo rss,pid,args --sort=-rss` plus per-process `VmSwap` from
`/proc/<pid>/status`. On this box the converter holds ~492 MB RSS + ~2.5 GB swap; every other
process (smbd, prometheus, synolog daemons) is under 11 MB. `%MEM` in `ps` understates it —
it ignores swap.

## Adding swap on DSM

Layout already present: `/dev/md1` 2.0 GB (priority -1), `/dev/zram0` + `/dev/zram1` 549 MB each
(priority 1, both fill first and sit at 100%).

Working recipe (`fallocate` fails on this btrfs, `dd` is used):

```bash
sudo mkdir -p /volume1/.swap && sudo chattr +C /volume1/.swap   # NOCOW must be set first
sudo dd if=/dev/zero of=/volume1/.swap/swapfile bs=1M count=8192 status=none
sudo chmod 600 /volume1/.swap/swapfile
sudo btrfs property set /volume1/.swap/swapfile compression ""
sudo mkswap /volume1/.swap/swapfile
sudo swapon -p 0 /volume1/.swap/swapfile    # priority 0 sits between zram (1) and md1 (-1)
```

Hazards already hit:

- **A killed ssh job does not kill its remote `dd`.** Three orphan `dd` processes kept zero-filling
  the file *after* `mkswap`/`swapon`, growing it from 4.06 GB toward 5.3 GB and writing into a live
  swap area. Always `ps -eo pid,args | grep "[d]d if=/dev/zero"` and kill them before
  `mkswap`, and confirm the size is stable before `swapon`.
- `swapoff` on a thrashing box gets OOM-killed; treat swapoff as unavailable while memory is full.
- A swapfile is **not re-enabled across reboot** on DSM — nothing persists it.
- Swapfile on `/volume1` (btrfs on LVM) works; `chattr +C` on the directory is what makes it legal.

## What swap does and does not fix

Extra swap adds *capacity*, so a process that is still growing can continue. It does nothing for a
process that is only faulting pages back in: the new swapfile stayed at 0 used while the converter
was stalled, and CPU time did not move. Do not present "added swap" as a fix for a thrash stall —
check `/sys/block/sdr/stat` and CPU time afterwards.

## Watcher

`~/.local/state/homelab/btrfs-watch.sh` (v4) polls every 60 s, chains the SG window when WD verifies,
and fails on `ABORT`, a bad `blkid`, or 6 minute-ticks with no process *and* no success state.
It dies with the machine and leaves a stale pidfile; re-arm with
`bash ~/.local/state/homelab/btrfs-watch.sh &` and confirm `pgrep -fl btrfs-watch`.
Log: `~/.local/state/homelab/btrfs-watch-20261103.log`.
