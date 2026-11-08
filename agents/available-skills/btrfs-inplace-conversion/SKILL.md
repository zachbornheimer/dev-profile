---
name: btrfs-inplace-conversion
description: Convert an ext2/3/4 disk to btrfs in place with btrfs-convert, including how to diagnose a conversion that "has been running for days" without progress, the -d flag that turns a multi-day stall into minutes, how to read progress at all, what rollback can and cannot do, and the verification gate that proves no files were lost. Use before converting any multi-TB disk, or when btrfs-convert appears stuck.
---

# In-place ext4 → btrfs conversion

## The failure this skill exists for

`btrfs-convert` looks alive for days and converts nothing. Real case, 2026-11-07, Synology DS218+
(2 GB RAM, Celeron J3355) converting a 4 TB ext4 with 3.03 TB used:

- elapsed 32 h, **CPU time 11 minutes**, device writes **35 MB**
- `State: D (disk sleep)`, load 10.5, IO-wait 10.4, CPU 0.09
- kernel stack `wait_on_page_bit_killable ← __lock_page_or_retry ← handle_mm_fault`
- every swap device 100% full, ~110 MB RAM available

It was not slow. It was in a swap-fault livelock: btrfs-progs v6.x **checksums every data block by
default**, so it reads the whole used data set; that working set exceeds RAM, spills to swap, and the
process spends all its time faulting pages back in instead of converting.

## Diagnose in one pass (do this before waiting another hour)

```sh
dev=sdr1; pid=<btrfs-convert pid>
cat /sys/block/$dev/stat            # field 3 = sectors read, field 7 = sectors written
sudo cat /proc/$pid/io              # rchar vs read_bytes
sudo cat /proc/$pid/stack | head -8 # what the process is actually waiting on
ps -o pid,state,etime,time,pcpu,rss -p $pid
```

How to read it:

- **`sectors written` is the only honest progress counter.** 35 MB after days means nothing has been
  converted, whatever the elapsed time says.
- `rchar` frozen while `read_bytes` climbs = the process is not reading the device; the kernel is
  swapping pages in on its behalf.
- CPU time flat over many hours with `State: D` = livelocked on memory, not computing.
- Attribute memory before blaming the disk:

  ```sh
  for d in /proc/[0-9]*; do s=$(grep -m1 ^VmSwap: $d/status 2>/dev/null | awk '{print $2}'); \
    [ -n "$s" ] && [ "$s" -gt 20000 ] && echo "$s kB $(cat $d/comm)"; done | sort -rn | head
  ```

  One `btrfs-convert` holding RSS plus several GB of swap on a 2 GB box is the whole answer.
- `swapon -s` "used" can be misleading; per-process `VmSwap` is the trustworthy attribution.
- No usable progress line? `nohup` block-buffers the `--progress` stream, so the log stays 0 bytes and
  the carriage-return progress output never flushes.

## The fix: skip the data checksums

```sh
btrfs-convert -d -i -L --uuid copy -O ^free-space-tree /dev/sdX
```

- `-d` / `--no-datasum` — no checksum pass, so **the data is never read**. This is what turns a
  livelocked multi-day run into ~12 minutes: only metadata is rewritten (2.8 GB written for a 3 TB
  filesystem). Files get `NODATASUM`, i.e. metadata is checksummed but data blocks are not, so scrub
  will not detect bitrot in those files. CoW and snapshots work normally. Restore checksums later
  with `btrfs filesystem defrag -r -c <mountpoint>` (rewrites everything).
- `-i` / `--no-xattr` — xattr copy fails `-95` on some kernels; usually only netatalk/`@eaDir` caches
  and a few Synology ACLs are lost.
- `-O ^free-space-tree` — lower metadata memory use.
- Keep `-L` (label) and `--uuid copy` (stable UUID for fstab/exports).

Run it so progress is visible:

```sh
sudo sh -c "cd /path && stdbuf -oL -eL nohup btrfs-convert.static -d -i -L --uuid copy \
  -O ^free-space-tree /dev/sdX > convert.out 2>&1 < /dev/null &"
sudo tail -c 400 convert.out | tr '\r' '\n' | tail -3   # "Copy inodes [ 5308/ 19777]"
```

The `Copy inodes [n/total]` counter is the one readable percentage; it accelerates near the end.
`Conversion complete` plus a btrfs `blkid` is the success signal.

## Rollback semantics

`btrfs-convert -r /dev/sdX` only works if a btrfs superblock was written. `No valid Btrfs found on
/dev/sdX` is good news, not an error: the converter never got past its read phase, so the filesystem
is still plain ext4 and needs no rollback. A successful conversion leaves `ext2_saved/` in the new
filesystem as the rollback image — keep it until you have verified and lived with the result.

Killing is safe: a process blocked in `wait_on_page_bit_killable` is killable. Kill the _wrapper_
script first so it cannot restart or record a failure, then the converter.

## Verify before saying done

Never accept "conversion complete". Compare against a listing taken **before** the conversion:

```sh
# before: path \t type \t size \t mode \t owner:group \t nlink
awk -F'\t' '$2=="f"{n++; s+=$3} END{print n, s}' listing.before.tsv
# after
find /mnt -xdev -type f -printf '%s\n' | awk '{n++; s+=$1} END{print n, s}'
```

Identical file count and identical **total bytes** is the proof. Then:

```sh
stat -f -c %T <mountpoint>                    # btrfs
btrfs filesystem show /dev/sdX                # FS bytes used vs device used
btrfs filesystem df <mountpoint>              # Data used, Metadata used
dd if=<a real file> bs=1M count=8 | md5sum    # data reads back, not sparse zeros
echo probe > <mountpoint>/.probe && sync && rm <mountpoint>/.probe
```

Run `e2fsck -fn /dev/sdX` **before** converting (all 5 passes, no repairs), and record the mount set
before and restore it after, so shares come back with the same targets.

## Synology / DSM gotchas

- `swapoff` is blocked outside Synology's own framework: `*ERROR* use swapoff without syno framework!`
  A swapfile added by hand therefore cannot be detached from a shell; it disappears on reboot.
  Adding one works: `mkdir -p /volume1/.swap && chattr +C /volume1/.swap`, then `fallocate`/`dd`,
  `mkswap`, `swapon`. Extra swap does **not** fix a fault livelock — the process is not allocating,
  it is faulting pages back in.
- `blkid` can keep reporting `ext4` for the whole run; the btrfs superblock is written at the end.
- Restore mounts with the box's own script rather than hand-mounting:
  `sh /usr/local/etc/rc.d/S99media-usb.sh start` (mounts by label, recreates the bind mounts).
- Check USB link speed before blaming the disk: `cat /sys/bus/usb/devices/*/speed`
  (5000 = USB 3, 480 = USB 2). A 4 TB conversion over USB 2 is a different problem than thrash.
- Record a terminal state for the window tooling (`WINDOW-OK`) plus a provenance line in its log, or
  the next run and any watcher treat the conversion as still in flight.

## Order of operations

1. Stop writers and unmount the filesystem.
2. `e2fsck -fn /dev/sdX` — must be clean; `e2fsck -fp` if it reports anything.
3. Record the pre-conversion listing (path, type, size, mode, owner) and the mount set.
4. `btrfs-convert -d -i -L --uuid copy -O ^free-space-tree /dev/sdX` under `stdbuf`.
5. Watch `sectors written` in `/sys/block/<dev>/stat`; a flat counter for 10 minutes means stop and
   re-diagnose rather than wait.
6. Mount, restore binds, compare file count and total bytes, read and write a real file.
