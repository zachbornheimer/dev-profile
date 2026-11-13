---
name: synology-low-ram-btrfs-convert
description: "Convert a large ext4 USB drive to btrfs in place on a low-RAM Synology NAS (DS218+ class), including how to diagnose and break the btrfs-convert swap-thrash livelock with -d, and how to verify nothing was lost."
---

# Converting a large ext4 drive to btrfs on a low-RAM Synology

Learned on a DS218+ (Celeron J3355, 1.8 GB RAM, btrfs-progs v6.17.1) converting a
4 TB ext4 USB drive holding 3.03 TB in 19,777 files. A default-flag attempt burned
2 days and wrote 35 MB; the `-d` run finished in 12 minutes.

## The failure mode to recognise

`btrfs-convert` **computes data checksums by default**, so it reads every data block
(3 TB here). On a 2 GB box the working set spills into swap, swap fills, and the
process enters a page-fault livelock:

- `ps` state `D`, kernel stack `wait_on_page_bit_killable` ← `__lock_page_or_retry` ← `handle_mm_fault`
- CPU time frozen (11 min in 24 h), `rchar` frozen, `read_bytes` advancing = swap-in only
- load average 10+ with IO ≈ load and CPU ≈ 0
- device write sectors flat (`/sys/block/<dev>/stat` field 7)

Adding swap does **not** fix this: the process is faulting pages in, not allocating,
so a fresh swapfile stays at 0 used. Do not spend time on more swap.

## Procedure

1. **Baseline the denominators** so you can prove integrity later. Before converting,
   record for the fs: block size and used blocks (`e2fsck` summary gives
   `N/M blocks`), file count, and a `path<TAB>type<TAB>size<TAB>mode<TAB>owner<TAB>links`
   listing. Total bytes = sum of the size column for `type==f`.
2. **Stop any wrapper and the converter**, wrapper first so nothing restarts it:
   `sudo kill -9 <convert-pid>; sudo kill <wrapper-pids>`. The livelock wait is
   killable, so SIGKILL lands.
3. **Check whether a rollback is even needed**: `blkid <dev>`. If it still says
   `ext4`, the converter never wrote a btrfs superblock and `btrfs-convert -r <dev>`
   will answer `No valid Btrfs found` — there is nothing to roll back and the ext4 is
   intact. That is the expected result after a stalled pre-write run.
4. **fsck read-only, unattended**: `nohup e2fsck -fn <dev> > e2fsck.out 2>&1 &`, then
   poll for completion. All five passes must report no repairs.
5. **Convert with datasums disabled**:
   ```
   cd /volume1/scratch-conversion
   sudo stdbuf -oL -eL nohup bin/btrfs-convert.static \
     -d -i -L --uuid copy -O ^free-space-tree <dev> > convert.out 2>&1 &
   ```
   - `-d` = `--no-datasum`: skips the full data read; converted files get NODATASUM.
   - `-i` = xattrs not copied (the default xattr copy fails with -95 on DSM's kernel).
   - `-O ^free-space-tree` reduces metadata memory use.
   - `stdbuf` matters: without it `nohup` block-buffers the `\r` progress stream and
     the log stays at 0 bytes, leaving you with no progress signal at all.
6. **Watch two signals**: the `Copy inodes [N/19977]` lines in the log (real
   percentage) and `/sys/block/<dev>/stat` write sectors (ground truth of commits).
   Healthy is 45–85 % CPU with writes climbing; the stalled mode is 0 % CPU and flat
   writes. Data blocks are not copied, so expect ~3 GB of writes for a 3 TB
   conversion, not 3 TB.
7. **Verify before declaring done**:
   - `blkid` → `TYPE="btrfs"`, original UUID and label preserved
   - `btrfs filesystem show <dev>` and `btrfs filesystem df <mount>`
   - `ext2_saved` directory present (keeps rollback possible)
   - file count and total bytes identical to the step-1 baseline
   - read test on a real recorded file (dd 8 MB | md5sum) plus a write probe
8. **Restore DSM mounts** with its own script rather than hand-mounting:
   `sudo sh /usr/local/etc/rc.d/S99media-usb.sh start` — it mounts by label and
   recreates every declared bind mount.
9. **Record the terminal state** in the window/state file the tooling reads (e.g.
   `echo WINDOW-OK > win-<drive>/state`) plus a one-line provenance entry in its log,
   so no later run treats the window as dangling.

## DSM quirks that bite

- `swapoff` outside Synology's framework is refused by their kernel module:
  `*ERROR*, use swapoff without syno framework!`. A swapfile you added from a shell
  cannot be detached again; it survives only until the next reboot (`rm` on it also
  fails with EPERM while attached).
- `vmstat`, `pgrep`, `find -printf` are absent or restricted; use `/proc/vmstat`
  (`pswpin`/`pswpout`), `/proc/<pid>/io`, `/proc/<pid>/stack` and
  `ls -l /sys/block/<dev>/stat`.
- zram swap can hold pages of an already-dead process; `swapon -s` then disagrees with
  the per-process `VmSwap` scan. Trust the per-process scan.
- Synology mounts USB shares under `/volumeUSB2/<label>` and binds media paths from
  there; the bind set is recorded beforehand as `mounts.before`.

## Cost of `-d`

NODATASUM means metadata is checksummed but data blocks are not, so scrub will not
detect bitrot in the converted files. Restore checksums with
`btrfs filesystem defrag -r -c <mount>` — a full local rewrite, hours on USB.
