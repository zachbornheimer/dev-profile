---
name: diagnose-omp-memory-bursts
description: "Diagnose omp processes ballooning to many GB, UI freezes (ui.loop-blocked), or Mac jetsam/watchdog panics caused by omp/bun memory on this machine"
---

# Diagnose omp memory bursts and freezes

Proven on 2026-11-06. The root cause was in `capability-replicas`, not omp. The channel store `~/.local/state/capability-channels/completions.jsonl` had grown to 2 GB of duplicate records. Every omp re-parses that whole file on every capability wake. Fix: commit 49a8289ff2, `mastra/src/channel/store.ts`.

## 1. Confirm it was memory (after a crash)
- Kernel panics and low-memory kill reports are in `/Library/Logs/DiagnosticReports/` (`panic-full-*.panic`, `JetsamEvent-*.ips`, `omp_*.diag`).
- Jetsam `.ips` files: line 1 is a header and the rest is JSON. Sum `rpages * 16384` per process `name` to get footprint per process.
- WindowServer or watchdogd watchdog panics that follow jetsam events mean memory starvation (inference; the panic text never says so).

## 2. Find when each process froze
- Each omp process logs to `~/.omp/logs/omp.<date>.<pid>.log` (JSON lines).
- `rg 'loop-blocked","blockedMs":[0-9]{4,}'` lists freezes of 1 s or longer. The freeze started at the logged timestamp minus `blockedMs`.
- Match those start times against session JSONL entries and capability wake `created_at` values. A freeze that begins about 1 s after each wake points at the wake/channel path.

## 3. Profile a fresh omp, without touching the session in use
- An installed, compiled `omp` honors `BUN_OPTIONS="--cpu-prof --cpu-prof-dir=/tmp/bunprof"`.
- Run it in a Python `pty.fork()` harness:
  - submit a prompt that causes several background `run_command` + `wait` rounds (each one produces a wake);
  - log the process-tree RSS (resident memory) every second;
  - exit cleanly (ESC, ESC, `/exit`) or SIGTERM so the profile file gets written.
- Aggregate the `.cpuprofile`: self and inclusive time per `functionName url:line`. In the 2026-11-06 run the parser `parseChannelFile` dominated.

## 4. Check the channel store directly
- `ls -la ~/.local/state/capability-channels/`. A size over a few MB is suspect.
- Compare total line count with distinct `"id"` count. A large ratio means duplication.
- Compaction:
  1. Back up first with `cp -c`.
  2. Stream the file, keeping the first copy of each line, into a temp file.
  3. Before swapping, copy over lines other processes appended during the run (the tail past the original read offset).
  4. Swap in with `os.replace`.

## 5. Ship a capability-replicas fix
- Work in a worktree (`wt switch --create ... --base main`) and merge with `wt merge -y main`. The extension runs from the live checkout, so a merge goes live with no rebuild.
- `mastra`'s `test` script is vitest. New tests go in `*.test.ts` files that import `bun:test` and run with `bun test <file>`; vitest skips those files.
- Many existing suites already fail under bun. Diff the failure list with and without your change rather than expecting all green.
- Restart the gateway: `launchctl kickstart -k gui/$(id -u)/com.zysys.capability-gateway`, then poll `http://127.0.0.1:4600/healthz`.
- omp sessions started before the fix keep the old code until they restart.
