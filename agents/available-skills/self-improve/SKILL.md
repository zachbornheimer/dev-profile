---
name: self-improve
description: Mine recent corrections across Claude Code, Codex, Cursor, and OpenCode — cluster recurring ones, adversarially verify each candidate, and distill survivors into gotcha entries or CLAUDE.md rules as proposed diffs for human approval. Run on demand or weekly via /schedule.
---

# Self-Improve

Turn the corrections you give me into rules I can't repeat. The loop has four
stages: harvest → cluster → adversarial verify → propose. Nothing lands without
your eyes on it.

## 1 — Harvest

```bash
uv run /Users/zbornheimer/.claude/skills/self-improve/scripts/harvest-corrections.py --days 30
```

Streams candidate corrections as NDJSON to stdout. Fields per line:
`text`, `context`, `tool`, `repo_or_project`, `approx_date`.
Skip notes (unreadable formats, absent dirs) go to stderr.

Save to a temp file for the next steps:

```bash
... --days 7 > /tmp/corrections.ndjson
```

## 2 — Cluster (parallel subagents)

Spawn one subagent per thematic bucket (naming, facades, error handling, testing,
UX, commit discipline, etc.). Each reads the NDJSON and returns a compact summary:

- Cluster label + representative examples (≤ 3)
- Frequency: how many distinct corrections hit this class
- Which tools / repos it appeared in

Run the buckets in parallel — they're independent reads of the same file.

## 3 — Adversarial verify (skeptic per cluster)

For each cluster that survived clustering, spawn a skeptic subagent with one
question:

> "Would this rule have caught a _real, distinct_ mistake in the harvested
> sessions — or is it a one-off, or already covered by an existing rule in
> `~/.claude/CLAUDE.md` or `skills/`?"

Gate: **≥ 3 distinct corrections of the same class** to proceed. A rule that
would not have changed a prior outcome is noise — reject it.

The skeptic must also check whether any existing CLAUDE.md line or skill
`references/gotchas.md` already covers this pattern before recommending it.

## 4 — Distill (proposed diff only — never auto-apply)

Survivors go to exactly one of three targets:

| Scope                    | Target                                                |
| ------------------------ | ----------------------------------------------------- |
| Specific, localized      | `skills/<name>/references/gotchas.md` — a new bullet  |
| Cross-cutting behavioral | `~/.claude/CLAUDE.md` — a new always-on line          |
| Skill workflow rule      | `skills/<name>/SKILL.md` — under the relevant heading |

Output a unified diff. Present it. You apply it with `patch -p1 < proposed.patch`
or edit manually. The loop is a _proposal_ system — it never touches live config.

## Gotchas

- One-offs fail the adversarial gate on frequency alone. Don't loosen the ≥ 3
  threshold — the signal-to-noise ratio in user corrections is low.
- The harvester reads only **user turns**. Model turns are not corrections; the
  heuristic already filters them out.
- Corrections that appear in only one repo may be project-specific, not a
  general rule. Note that in the cluster; weight it lower.
- Never paste raw correction text verbatim into a proposed rule. The rule captures
  the _pattern_, not the content — PII and context stay in the logs.
- Read `references/schedule.md` for the weekly /schedule wiring and cadence
  rationale.
