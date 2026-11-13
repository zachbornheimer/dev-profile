---
name: macos-time-machine-slow-backup
description: "Diagnose a slow macOS Time Machine backup to an external drive (read-only checks: USB link speed, throughput, item rate, Spotlight, exclusions)."
---

# Slow Time Machine backup: diagnose

Run every command through run_command. Everything here is read-only; change nothing without the user asking.

1. Status and progress: `tmutil status` (Percent, bytes, totalBytes, TimeRemaining) and `tmutil destinationinfo`.
2. Real throughput: `log show --last 15m --predicate 'subsystem == "com.apple.TimeMachine"' --info | grep -A3 CopyProgress | tail`. It reports `MB/s`, `avg` MB/s and `items/s`. Low items/s with low MB/s means many small files; the destination or link is the limit.
3. **USB link speed (most common cause):** find the drive with `diskutil list external` and `diskutil info diskN` (Device / Media Name, Protocol). Then `system_profiler SPUSBHostDataType | grep -B3 -A12 -i "<media name>"` and read `Link Speed`. 480 Mb/s means it negotiated USB 2.0 (about 35 MB/s ceiling, far less in practice). USB 3 should show 5000 or 10000 Mb/s. Cause is usually a charge-only or USB 2 cable, a hub or dock, or a bad port.
4. Other factors: drive may be an HDD (`diskutil info` often does not say; check the model). Spotlight indexing the backup volume (`mdutil -s <mount>`; `sudo mdutil -i off <mount>` helps the first backup). Large or high-file-count paths (node_modules, simulators, VMs) can be excluded with `tmutil addexclusion`; check with `tmutil isexcluded <path>`. Close the Time Machine Settings window, which can use high CPU.
5. Fix order: swap in a known USB 3 / 10 Gb/s data cable, plug directly into the Mac, `tmutil stopbackup`, replug, recheck Link Speed, restart the backup. A first backup resumes.

Gotchas: `iostat -w` and `system_profiler | head` chained with `iostat` get auto-placed in a herdr pane by run_command; run them separately, or skip iostat and use the CopyProgress log lines.
