---
name: moshi-omp-inbox
description: "Diagnose why Moshi's agent inbox is missing Oh My Pi sessions or showing incomplete names."
---

# Moshi inbox vs Oh My Pi sessions

Use when the user says Moshi (often dictated as "Moshe") is missing open omp sessions, or session names did not carry over. Pro does not cap the inbox.

## What the inbox is

Not a live list of open omp tabs. `moshi-hook` forwards hook events. One row per session, updated in place. A row exists only after that session emits an event.

Announced events: first prompt (`session_started`), a finished turn (`task_complete`), an approval or question. Restarting omp loads `~/.omp/agent/extensions/moshi-hooks.ts`; it does not create a row. Idle tabs stay invisible.

Open terminals live in the session picker and the Workspaces sidebar after an SSH/Mosh connect, not in the inbox. Finished rows leave the active inbox after 10 minutes; anything older than 6 hours auto-archives.

## Names

The hook never reads the omp tab title. Titles it sends:

- first prompt: `OMP session started`
- later prompts keep the previous event title
- finished turn: first 80 characters of the assistant reply (body is the first 200 characters of the user prompt)
- approval: `OMP needs approval`

Named forks and omp subagents are dropped on purpose (`isChild && agentSource === "omp"` returns before send). Their titles never leave the laptop.

## Diagnose on this Mac

1. `moshi-hook doctor` — daemon running, paired, omp hooks current. Agents already running when hooks changed must be restarted; they read hook config at startup.
2. `rg 'no push token|suppressing' "$HOME/Library/Application Support/Moshi/hook.log"` — `no push token registered; suppressing low-priority agent events` drops `session_started` and `task_complete`. That is the phone, not the account. Fix: iOS Settings → Notifications → Moshi → Allow, open Moshi, send its test notification, then type one line in the omp tab that should appear.
3. Compare `source=omp session=` lines in that log with `ps` omp processes. A running `--resume` session absent from the log never announced itself.
4. Settings that change what arrives, in `~/.config/moshi/config.toml` / `moshi-hook set`: `suppress-push-without-mux` (default on, silences pushes outside tmux/herdr; inbox still gets the event), `suppress-nested-agent-push`, `usage-collection` (usage rings only, not the inbox).

Do not treat a sparse inbox as a missing install when doctor says omp hooks are current.
