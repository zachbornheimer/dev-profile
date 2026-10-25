---
name: harness-efficiency
description: >-
  Use when auditing coding-agent sessions for waste, running /harness-efficiency,
  improving harness efficiency, converting repeated friction into a skill,
  command, hook, or Linear item, or checking whether a prior harness fix still
  helps. Not for summarizing sessions into notes. Not a replacement for /learn
  (Grok skill/plugin usage) or self-improve (correction-to-gotcha diffs).
user-invocable: true
argument-hint: "discover|index|analyze|research|audit|eval|worst|scorecard [--days N | --since-last] [--harness NAME] [--json] [--limit N] [--session ID]"
---

# Harness efficiency

Audit local coding-agent sessions across harnesses. Scripts find recurring waste
and map it to the smallest durable primitive. Original session files are
**read-only** — never load raw transcripts into this conversation.

Claude's `session-forensics` lives at `~/.claude/agents/session-forensics.md`.
Grok already lists it as a spawn type (Claude-compat). Use it for Claude JSONL
only. It pins `model: sonnet` (Grok ignores / cannot pin that) and Claude tool
names; the procedure (stream with python3, never load the transcript) still
works here. Do not send Grok/Codex/Cursor transcripts to that agent. For those,
spawn `explore` with the same eight-section brief plus python streaming of that
harness's files.

## Run

```bash
python3 ~/.agents/available-skills/harness-efficiency/scripts/harness_efficiency.py discover --json
python3 ~/.agents/available-skills/harness-efficiency/scripts/harness_efficiency.py research --json
python3 ~/.agents/available-skills/harness-efficiency/scripts/harness_efficiency.py audit --days 14
python3 ~/.agents/available-skills/harness-efficiency/scripts/harness_efficiency.py worst --limit 8 --json
python3 ~/.agents/available-skills/harness-efficiency/scripts/harness_efficiency.py scorecard --session ID
```

Default window is `--days 14`. `--since-last` uses the previous audit. `--harness NAME`
limits one vendor. `--json` prints machine output on discover/research/worst.

`research --stamp` refreshes the overlay `checked_at`. `audit --refresh-research`
is the audit-time alias. `--refresh-research` is not a top-level flag.

After `audit`, read `<run_dir>/report.md` then `<run_dir>/patterns.json`. Then:

1. Run `worst --limit 8 --json`.
2. Spawn one forensics investigator per expensive session (cap 8, parallel):
   `session-forensics` if harness is claude, else `explore` with
   [references/scorecard.md](references/scorecard.md). Each writes
   `$HE_STATE/forensics/<id>.md`. Never load transcripts into the parent.
3. Read those reports (not JSONL). Load `typesafe-ai`; run
   `scripts/judge_scorecard.py` on each report; compose primitives in code from
   those answers. Do not add a serial LLM pass that re-asks the same 2a–2d in
   prose.
4. File Linear per [references/linear.md](references/linear.md).

Per session: identity · intent · outcome (verified vs claimed) · fit (vs human,
turns/tokens, subagents vs tasks) · friction · counterfactual · primitive.
Across sessions: stick · gate-vs-edit · over-parallel vs missed-parallel.

`eval` must pass before treating the skill as working:

```bash
python3 ~/.agents/available-skills/harness-efficiency/scripts/harness_efficiency.py eval
```

## Map a finding

Pick the primitive from [references/primitives.md](references/primitives.md), including
where it lives (memory, skill, script, hook, schedule, or nothing). File
Linear items per [references/linear.md](references/linear.md) (search first; skip
one-offs unless severe). Taxonomy:
[references/taxonomy.md](references/taxonomy.md).

| File                                                 | When to load                                 |
| ---------------------------------------------------- | -------------------------------------------- |
| [references/taxonomy.md](references/taxonomy.md)     | Finding shape, kinds, prior-join             |
| [references/primitives.md](references/primitives.md) | command vs skill vs hook vs subagent         |
| [references/harnesses.md](references/harnesses.md)   | Session paths and formats                    |
| [references/linear.md](references/linear.md)         | Project, search-before-create, known tickets |
| [references/research.json](references/research.json) | Cached 2026-09-18 vendor notes (ttl 7d)      |
| [references/scorecard.md](references/scorecard.md)   | Forensics brief and per-session checklist    |
