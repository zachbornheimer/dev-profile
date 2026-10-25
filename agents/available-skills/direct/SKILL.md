---
name: direct
description: Use when the user says "/direct", "let me do this hands-on", or "stop delegating for a bit" — allows this main session (Claude Code or Grok) to edit files and run mutating shell commands directly for the rest of the session, bypassing the orchestrator-only PreToolUse gate.
user-invokable: true
---

# Direct mode

Turns off the orchestrator-only gate (`~/.agents/hooks/orchestrator-only.py`) for
**this session only**, so Edit/Write/NotebookEdit and mutating Bash commands stop
being denied. Use for a genuine hands-on stretch, not as a default.

## How to invoke

```bash
~/.agents/hooks/direct-mode.py on
```

This is the one Bash command the gate itself allows the main session to run
without already being in direct mode (see `orchestrator-only.py`'s
`direct-mode.py` exception) — nothing else needs to run first.

The script binds `GROK_SESSION_ID` when set, else `CLAUDE_CODE_SESSION_ID`, else
the newest per-session state file. Print exactly the script's own output line
back to the user (`direct mode ON for session <id>`) — do not paraphrase it,
since that line is the only confirmation that the marker landed on the right
session. On Grok, `<id>` must equal `$GROK_SESSION_ID`.

If the script instead prints `no session state found yet`, run any read-only
command first (e.g. `git status`), then retry — that path is only for a session
with neither env var set yet.

## Turning it back off

Load the `orchestrate` skill (or say "/orchestrate") when done working
hands-on — direct mode does not expire on its own.

User-invoked only. The model never proposes /direct as a way around a denial.
