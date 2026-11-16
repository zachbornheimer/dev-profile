# Removed-harness inventory

Supported harnesses: **omp** and the **Codex desktop app**. Everything below was
removed because it served only an unsupported harness, or is kept because omp or
Codex desktop still needs it. Each entry names the harness it served.

## Removed

### Dependency declarations and ACP adapters (PR #153)

- `claude-agent-acp` pin in `profile/mise.toml`: Claude Code ACP adapter.
- `codex-acp` pin in `profile/mise.toml`: Codex CLI ACP adapter.
- zed `claude-acp` agent-server block: Claude Code in Zed.
- `apps/opencode/` (config and service files): OpenCode.

No removed-harness package, SDK or ACP entry remains in any manifest or lockfile.

### Code paths and config (this change)

- `agents/available-skills/find-session/**` (resolver, status helper, tests):
  Claude Code session ids.
- `agents/hooks/worktree-provision.py`, `worktree-cleanup.py` and
  `lib/worktree_{provision_git,provision_tools,provision_worktrunk,cleanup_git,cleanup_worktrunk}.py`,
  with their tests: Claude Code `WorktreeCreate` and `WorktreeRemove` events.
- `agents/hooks/tip-verify-rm-deny.py`, `lib/tip_verify_rm_deny.py`: tip
  locks of the retired message-board tool.
- `apps/agent-hooks/hooks.toml` rows and events: `Notification`,
  `WorktreeCreate`, `WorktreeRemove`, `ElicitationResult`, `StopFailure`,
  `PermissionDenied`, the Claude-skills lint row and the tip-lock row:
  Claude Code. `[defaults] agents` is now `codex`, `mastra`.
- `agents/hooks/shared-checkout-guard.py`, `subagent-model-guard.py`,
  `relocate-synced-skills.py`, `prompt-submit-capabilities.sh`,
  `session-recall.sh`: Claude Code worktree exemption, untyped `claude`
  subagent handling, `~/.claude/skills` relocation, Grok and Claude child
  processes.
- `agents/bin/memory-learn`, `bin/lib/sessions.py`, `bin/lib/model_passes.py`:
  Claude, Grok and Cursor transcript readers and the Cursor sweep. Model calls
  now use `omp -p --model`.
- `agents/available-skills/learnings/src/learnings/{transcript,cli}.py`: Claude
  session-id resolver.
- `agents/available-skills/harness-efficiency/scripts/he_parse.py`,
  `harness_efficiency.py` and references: Claude Code, Cursor, Grok, Gemini CLI,
  Copilot CLI and OpenCode session parsers. Indexing is Codex only.
- `agents/available-skills/self-improve/scripts/harvest-corrections.py`:
  Claude Code, Cursor and OpenCode harvesters.
- `agents/available-skills/agent-hooks/scripts/audit-catalog.py` and
  `references/events-and-harnesses.md`: agent aliases other than `codex` and
  `mastra`.
- `agents/agents/{learning-applier,execution-forensics}.yaml`: Claude settings
  and transcript-store instructions.
- `agents/available-skills/typesafe-ai/scripts/constants.py` and
  `assume-session/SKILL.md`: `find-session` routing tuple and row.
- `agents/available-skills/verify/scripts/check-tests.sh`: Claude Code Stop-hook
  template.
- `agents/available-skills/i-have-adhd/agents/gemini.toml`: Gemini CLI.
- `shell/zsh/land-pr.zsh`: Claude Code and Copilot CLI drivers.
- `shell/zsh/aoe-agent.zsh`, `aoe-session-facts.py`: Claude and Grok session
  scanners and effort defaults. Session cwd resolves from omp and Codex stores.
- `home/Brewfile`: `cask "claude"` (Claude desktop). `codex-app` and `aoe` stay.
- `home/scripts/install-evident-output-mcp.sh`: `.claude/skills/cli-output`
  install candidate.
- Stale backups: `agents/bin/.patch/*.bak-*`, `kitty/kitty.conf.bak` (and its
  listing line in `kitty/light-theme.tomorrownight.auto.conf`),
  `voice-signing-call-agent/scripts/run-outbound-twilio.mjs.bak-20260930`.

### Docs and labels (PRs #152 to #160, #162 to #169)

Statements that Claude Code, Codex CLI, Grok Build, OpenCode, Hermes and other
tools are supported were removed or labelled legacy. `README.md`,
`agents/AGENTS.md` and `agents/private_AGENTS.md` state that only omp and the
Codex desktop app are supported.

## Kept, and why

- `AGENT_HOOKS_AGENT: "claude"` in `apps/omp/extensions/run-agent-hooks.ts`:
  the agent id omp's bridge announces to the `agent-hooks` binary.
- `~/.claude/hooks/state` and `~/.claude/goals` paths in shared hook settings and
  the goals hooks: live state directories those hooks read and write.
- Hook row name `permissiondenied-shell-denial-steer-py`: referenced by
  `agents/AGENTS.md` and `learn-from-transcript`. Only the `PermissionDenied`
  event was removed.
- `agents/hooks/lib/worktree_target_queue.py`: imported by `work-order-gate`.
- `completion_gate_claude_transcript.py`: the omp transcript decoder reuses it.
- Legacy transcript readers marked as such, stray-link guard lists in `aubx`,
  `aubx-skills` and `skills-add`, test fixtures.
- 1Password item names in `apps/ai/keys.env.op` and `triage-lead`: external
  vault entries, not code.
- The xAI "Grok" voice API in `voice-signing-call-agent`: a different product
  from Grok Build.
- Citations in `cache-hygiene.md` and generated data (`.zcompdump`,
  `repo-catalog.json`, `taxonomy.json`).
- `apps/opencode/service.json`: gitignored credential file left on disk, never
  committed.
