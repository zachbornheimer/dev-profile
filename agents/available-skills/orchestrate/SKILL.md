---
name: orchestrate
description: Use when the user says "/orchestrate", "back to delegating", or "stop editing directly" — turns direct mode back off, re-enabling the orchestrator-only gate so this session (Claude Code or Grok) goes back to prompting and delegating instead of editing files or running mutating commands itself.
user-invokable: true
---

# Orchestrate mode

Turns the orchestrator-only gate (`~/.agents/hooks/orchestrator-only.py`) back
on for this session by removing the direct-mode marker `/direct` set. This is
the default posture — use this to end a hands-on stretch, not to start one.

## How to invoke

```bash
~/.agents/hooks/direct-mode.py off
```

The script binds `GROK_SESSION_ID` when set, else `CLAUDE_CODE_SESSION_ID`, else
the newest per-session state file. Print exactly the script's own output line
back to the user (`direct mode OFF for session <id>`) — do not paraphrase it.
On Grok, `<id>` must equal `$GROK_SESSION_ID`.

From here, route implementation work through `prompt-writer` → `implement`
subagent as usual (see `~/.claude/CLAUDE.md`, "Route implementation through
subagents — always").

User-invoked only. The model never proposes /direct as a way around a denial.
