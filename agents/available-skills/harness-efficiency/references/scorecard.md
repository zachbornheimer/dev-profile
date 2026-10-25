# Session scorecard (forensics brief)

Load this when spawning a forensics investigator after `worst`. Do not paste it
into the parent. The investigator streams the transcript with `python3` and
never loads JSONL into context.

## Agent choice

- Claude JSONL (`harness: claude`): spawn `session-forensics`
  (`~/.claude/agents/session-forensics.md`).
- Grok / Codex / Cursor / others: spawn `explore` with this brief and stream
  that harness's files from `path` on the `worst` row. Do not send those
  transcripts to `session-forensics`.

Write `$HE_STATE/forensics/<session_id>.md` (default
`~/.local/state/harness-efficiency/forensics/`). Return the path plus a
one-paragraph verdict. Parent reads the report, never the JSONL.

## Eight sections

Use the eight standard sections in `~/.claude/agents/session-forensics.md`
("The eight standard sections"). Do not paste that agent file here.

1. Task
2. Time accounting
3. Tool tally
4. Hook friction
5. Repeated tool-input signatures
6. Token accounting
7. Liveness
8. Verdict

Time-accounting buckets (must sum to the span): Model working, Tool executing,
Waiting on a subagent, Waiting on the user, Host sleep or suspension,
Unexplained. Compute every duration from consecutive timestamps. Host sleep
needs corroborating stalled siblings; otherwise `0s -- no corroborating
evidence`. Stream with one `python3` pass; never `cat` or Read the transcript.

## Parent synthesis (after reports)

Load `typesafe-ai`; run `scripts/judge_scorecard.py` on each report; compose
primitives in code from those answers. Do not add a serial LLM pass that
re-asks the same 2a–2d in prose. File Linear from the composed answers.

Per session — issues + one primitive each, not n-grams:

| Field          | Ask                                          |
| -------------- | -------------------------------------------- |
| identity       | harness, id, path, model, window             |
| intent         | one task, or many piled on?                  |
| outcome        | verified vs claimed                          |
| fit            | vs a human; turns/tokens; subagents vs tasks |
| friction       | gates, retries, permission stops, hook loops |
| counterfactual | what the cheap path was                      |
| primitive      | one from [primitives.md](primitives.md)      |

Across sessions: stick, gate-vs-edit, over-parallel vs missed-parallel.

File Linear per [linear.md](linear.md). Search first; skip one-offs unless
severe.
