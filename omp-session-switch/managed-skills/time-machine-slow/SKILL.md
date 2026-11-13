---
name: time-machine-slow
description: "Use when a Time Machine backup on this Mac is slow or stalled, before blaming the USB cable, the drive, or the process table."
---

# Slow Time Machine

Measure the phase, Time Machine's own rate, and both disks before naming a cause. A slow USB link is a ceiling, not proof it is the limit.

## Checks

1. `tmutil currentphase`. `FindingChanges` is a scan, not a copy. `Copying` is the copy.
2. Time Machine's own rate, from its log (works without sudo):
   `log show --last 2m --predicate 'subsystem == "com.apple.TimeMachine"' --info | grep -A4 CopyProgress`
   It prints current and average MB/s and items/s, plus `ByItemCount` (done/total) and the path it is on. `tmutil status` `bytes` and `files` sampled 20 s apart give the same.
3. Destination I/O: `iostat -d -c 5 -w 1 <physical disk>`. The physical disk is the "APFS Physical Store" in `diskutil info "<volume>"` (for example disk4). The synthesized container (disk5) shows nothing. If the destination is idle while items/s is low, the limit is on the source or backupd side, not the cable or the drive.
4. Source I/O: `iostat -d -c 5 -w 1 disk0`. Many small reads (10k+ tps) from other processes can starve Time Machine. This is a hypothesis, not proven: `sysctl debug.lowpri_throttle_enabled` is 1, which makes throttled I/O yield. Testing it needs `sudo sysctl debug.lowpri_throttle_enabled=0` (resets on reboot).
5. Per-process disk I/O without sudo: libproc `proc_pid_rusage(pid, 4, buf)`; `ri_diskio_bytesread` is a u64 at byte offset 144 and `ri_diskio_byteswritten` at 152. Sample twice, 10 s apart. Root processes (backupd, mds_stores) are unreadable.
6. Time Machine Settings: while its window is open, it can send "stop backup attempt" to backupd. On 2026-11-08 that cancelled a running backup and unmounted the destination volume.

## Enumerating processes when ps hangs

`ps`, `top`, and `pgrep -c` hung or errored here under load. `libproc` was fast (under 1 s): `proc_listallpids`, then `proc_pidinfo` flavor 3 (BSD info: ppid, name, start time) and flavor 4 (task info: thread count at offset 84, resident bytes at offset 8). `proc_pidinfo` flavor 9 gives the cwd. Args need `sysctl kern.procargs2`; run it in a thread with a 2 s timeout.

## Do not

- Treat `kern.num_tasks`, `kern.num_threads` or `kern.num_taskthreads` as counts. They are limits (16384, 81920, 16384 on 2026-11-11), while 1281 real processes and 7394 threads were running. The earlier "process table full, 16384 tasks vs maxproc 16000" diagnosis (2026-11-07) was wrong.
- Keep recommending a cable swap after the user rejected it, or after the numbers contradict it.
- Write into the Time Machine volume to benchmark it. macOS denies that.
- Kill anything before the user agrees on what to reap.

## Cable fact

Apple's braided USB-C charge cable is USB 2 only (480 Mb/s in `system_profiler SPUSBHostDataType`). With a 40 Gb/s cable the ASM1352R enclosure shows "Limited to 5 Gb/s", which is its own cap. Use this only when the destination disk is busy and near the link ceiling.
