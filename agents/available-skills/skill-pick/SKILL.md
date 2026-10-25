---
name: skill-pick
description: >
  After a user turn, if this message has no <system-context> capability block,
  read ~/.agents/hooks/state/skill-picks/<session_id>.json and open each `load`
  skill by bare name with the read_skill capability.
---

# skill-pick

The agent-hooks `prompt.submit` hook runs `prompt-submit-capabilities.sh`, which
calls `capability run suggest_skills_tools_and_mcp` and appends its XML context as
the final block of the injected prompt, after the intent and project lines. Do not
re-run the capability or TypeSafe pick. The skills are already in the message, so
the per-session JSON below is only a fallback for a prompt that arrived without it.

If this message already has an `Intent:` line or a
`<system-context source="suggest_skills_tools_and_mcp">` block, stop.

Otherwise:

1. Resolve session id from `HERMES_SESSION_ID`, `GROK_SESSION_ID`, or Claude
   `session_id`. Do not invent one.
2. Read `~/.agents/hooks/state/skill-picks/<session_id>.json`.
3. If missing, empty (0 bytes), invalid JSON, `choice: none`, or `load` empty
   → stop. A 0-byte file means the announcer ran and wrote nothing usable.
4. Else open every `load` skill by bare name with `read_skill` before other
   tools (never construct file paths from the JSON; `paths` is a legacy field).

`split: true` is already handled as a blocked prompt. Do not implement that
`user_request` here. No tmux. No `assume-session`. Do not
`hermes skills install` a picked skill into `$HERMES_HOME/skills/`.
