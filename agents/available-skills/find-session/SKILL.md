---
name: find-session
description: Use to resolve any Claude Code session identifier (session id, a fragment of one, a session name, a job id, or a pid) to its transcript path — including when the id another tool printed (e.g. ListAgents) doesn't match any filename you can find by hand. Also use when asked to "find the session called X" or "where is session Y's transcript".
---

# find-session — resolve any Claude Code session identifier to its transcript

## The trap this exists for

`ListAgents` and similar tools print a short bracketed reference (e.g. `2c6e5e`)
that is **not** the transcript's session uuid. Globbing
`~/.claude/projects/*/2c6e5e*.jsonl` by hand fails even though the session
exists, because that short ref is a different identifier — usually a `jobId` —
and the transcript filename is the full `sessionId` uuid. Don't hand-guess the
mapping; run the script.

## Command

```bash
python3 ~/.agents/available-skills/find-session/scripts/find-session.py <identifier>
```

`<identifier>` can be any of:

1. an exact `sessionId` (full uuid)
2. a `sessionId` prefix
3. an exact session `name`
4. a case-insensitive substring of a session `name`
5. a `jobId`
6. a `pid`
7. `<harness>:<uuid>` for `grok`, `codex`, or `cursor` (agentmux's own
   cross-harness index — `claude-code:<uuid>` is accepted too and just
   strips the prefix before rule 1)
8. a bare uuid none of rules 1-6 match, when agentmux's own link records
   know it anyway

The script tries rules 1-6 in order and stops at the first one that produces
a match. It reads the live registry (`~/.claude/sessions/*.json`) first; if
nothing there matches, it falls back to globbing
`~/.claude/projects/*/<identifier>*.jsonl`, since an ended session's registry
entry disappears but its transcript file stays on disk. Rules 7 and 8 shell
out to `agentmux session <ref> --json` instead, skipped silently when
`agentmux` isn't on PATH or exits non-zero.

## Output

One JSON object per match on stdout, newest first, exit 0:

`transcript_path`, `session_id`, `name`, `cwd`, `status`, `kind`, `started_at`,
`size_bytes`, `mtime`, `matched_by` (which rule hit — `agentmux` for rules 7/8),
and `subagent_dir` when a `subagents/` directory exists next to the transcript.
Every match resolved via a Claude rule (1-6) also carries an `agentmux` key —
that session's `agentmux session claude-code:<uuid> --json` result (project
id, combined transcript, every sibling session) — when agentmux resolves it;
omitted otherwise, never guessed.

When nothing matches, it prints what it searched to stderr and exits 1 — it
never prints a path that doesn't exist on disk.

## Busy vs ended

`ListAgents` can still print `busy` after the transcript's last event is already
a session-end. This helper answers from the transcript tail instead:

```bash
python3 ~/.agents/available-skills/find-session/scripts/session-status.py <identifier>
```

`<identifier>` is the same set as `find-session.py`. stdout is one JSON object
with `busy` (bool) and `status` (`busy` or `ended`). `busy` is false when the
last parseable JSONL event is a session-end event (`session-end`, `session_end`,
or Claude's `ended-by-model`).

## Relation to `assume-session`

`assume-session` no longer uses a locator script: the `capability` MCP
(`run_get_recent_turns`, `run_create_session_handoff_doc`) resolves
`<harness>:<full id | prefix | latest | title words>` itself. This script takes
**any identifier** (uuid, prefix, name, job id, pid, or a cross-harness ref)
and, for identifiers Claude's own rules can't place, defers to `agentmux` —
the cross-harness session index every harness's link records feed into. Use it
when you need a Claude session's native transcript path, a job id or a pid.
