---
name: autolearn-output-has-no-collision-gate
description: "Use before adding, trusting, or blaming the autolearn/managed-skill loop: the duplicate gate does not cover ~/.omp/agent/managed-skills, and the nightly scheduler is not installed."
---

# Autolearn output has no collision gate

Two facts. Check both before treating the managed-skill corpus as trustworthy or
before writing a new autolearn artifact.

## 1. The duplicate gate excludes the directory that accumulates duplicates

`pretooluse-promotion-gate` is wired (`~/.config/agent-hooks/pipeline/pipeline.toml`
handler list), but its roots are hard-coded in
`~/.config/agent-hooks/pipeline/handlers/pretooluse-promotion-gate.rhai:62-63`:

```rhai
const OWNERS_ROOT = ".agents/available-skills";
const NEW_SKILL_ROOTS = [".agents/skills", ".agents/available-skills"];
```

`~/.omp/agent/managed-skills` is **not** in that list. That directory is the only
target of `autolearn_manage_skill` and holds the large majority of managed skills.
No entry in `~/.config/agent-hooks/hooks.toml` matches `autolearn_manage_skill`
at all, so the gate never runs on the tool that creates the duplicates.

Consequence: `autolearn_manage_skill` can create a near-duplicate of an existing
managed skill and nothing refuses it. Before creating one, grep the directory
yourself:

```
ls ~/.omp/agent/managed-skills
grep -ril "<mechanism word>" ~/.omp/agent/managed-skills/*/SKILL.md
```

Real duplicates found this way (2026-11): `time-machine-slow` /
`macos-time-machine-slow-backup`, `herdr-popup-key-does-nothing` /
`herdr-popup-key-silent-failure`, `parallel-edits-same-file-race` /
`never-parallel-edit-same-file`, and three overlapping zsh-cd skills.

Fix, if asked: add `~/.omp/agent/managed-skills` to `NEW_SKILL_ROOTS` and add the
tool name to the handler's matcher so one owner decides "how many skills say this".

## 2. The nightly loop is not scheduled

Do not assume the self-improvement or nightly-learning job runs. Observed:

- no plist in `~/Library/LaunchAgents` matching learn / improv / nightly / replica
- `launchctl list` shows no such job
- `mastra/bin/` has no learn / tick / nightly scheduler script
- `~/.local/share/capability-replicas/nightly.log` last written 2026-11-06;
  last `nightly:` line 2026-11-01
- last `self-improvement tick` 2026-11-05, both claims refused with
  `select candidate: ERROR: syntax error at or near "$6" (SQLSTATE 42601)`

The `$6` placeholder error is not a literal in the repo (the query is assembled
dynamically), so grep for the query builder, not for `$6`.

## What actually works

`learn_from_transcript` with `{ dispatch: false }` runs on demand and files Linear
issues. That is the reliable path. The automated half is dead-or-manual, and its
output directory has no collision gate.

Rule of thumb for what to capture: a per-machine fact (paths, account ids, ports,
layout) belongs in memory or `AGENTS.md`, not in a new
`~/.omp/agent/managed-skills` entry. A skill earns its place only when the
mechanism cannot be named before the run.
