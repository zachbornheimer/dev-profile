---
name: import
description: >
  Import a Claude Code session by UUID into this Grok session. Use when the
  user runs /import, types grok import <claude-code-uuid>, or pastes a Claude
  Code session UUID / JSONL path to continue that work here.
metadata:
  short-description: "Import a Claude Code session by UUID"
argument-hint: "<claude-code-uuid | jsonl-path>"
---

This is the TUI entry for `grok import <claude-code-uuid>`. It is the same
handoff Grok's session picker uses: `/resume-claude` plus the native id.

Set `TOOL=claude`. Set `SHARED_DIR="${SKILL_DIR}/../../bundled/skills/shared/resume-session"`.
If that directory is missing, use `${HOME}/.grok/bundled/skills/shared/resume-session`.
Read and follow `${SHARED_DIR}/CORE.md`, using `$ARGUMENTS` unchanged as the
session reference.

LOAD EVERY TURN. Not a sample. Not "the last stretch." Load every `## User` and `## Assistant` turn into context. Do not summarize recovered turns as a substitute for loading them.

Do not invent a Grok session id. Continue in _this_ session after the handoff.
The CLI form `grok import <uuid>` lives at `~/.grok/bin/grok-import` and launches
a new Grok with `/resume-claude <uuid>` in the transcript's working directory.
`--json` reports `nativeId` and `resumeCommand`; `sessionId` is always null
(this is not plugin `grok -r` compatibility).
