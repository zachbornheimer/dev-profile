# Events and harnesses

Source of truth: `src/events.rs` (`native_event_for`, `normalize_event`) and `src/installer.rs`
(`is_native_event`, install paths). Re-read those if this table and the code disagree.

## Canonical event to native name

| canonical                     | Claude / Codex / Grok / OpenCode              | Gemini                       | Copilot             | Hermes           |
| ----------------------------- | --------------------------------------------- | ---------------------------- | ------------------- | ---------------- |
| `session.start`               | SessionStart                                  | SessionStart                 | sessionStart        | on_session_start |
| `session.end`                 | SessionEnd                                    | SessionEnd                   | sessionEnd          | on_session_end   |
| `prompt.submit`               | UserPromptSubmit                              | BeforeAgent                  | userPromptSubmitted | pre_llm_call     |
| `tool.before`                 | PreToolUse                                    | BeforeTool                   | preToolUse          | pre_tool_call    |
| `tool.after`                  | PostToolUse                                   | AfterTool                    | postToolUse         | post_tool_call   |
| `turn.stop`                   | Stop                                          | AfterAgent                   | agentStop           | pre_verify       |
| `context.compact.before`      | PreCompact                                    | PreCompress                  | PreCompact (Pascal) | none             |
| `context.compact.after`       | PostCompact                                   | PostCompact (dead on Gemini) | n/a                 | n/a              |
| `subagent.start` / `.stop`    | SubagentStart / SubagentStop                  | same names, dead on Gemini   | n/a                 | subagent_stop    |
| `worktree.create` / `.remove` | WorktreeCreate / WorktreeRemove (Claude only) | n/a                          | n/a                 | n/a              |

Claude-only names pass through unchanged and select by their own name: `Notification`, `PostToolUseFailure`,
`PermissionDenied`, `StopFailure`, `ElicitationResult`, `Setup`, `UserPromptExpansion`.

Hermes quirks: only four tool names are renamed (`terminal`->`Bash`, `write_file`->`Write`, `patch`->`Edit`,
`delegate_task`->`Task`); others (e.g. `read_file`) keep their native name, so list those in the matcher. Output is
minimal: `{"context":...}` or `{"decision":"block"}`, and `on_failure` never fires (only exit 2 blocks).
`pre_llm_call` is the only event that injects context; a hook listing `session.start` runs there only when selected
by name or group. `pre_verify` is the continue-the-turn event but the installed selector does not match it yet
(`known-issues.md`).

## Where `install` writes

| harness  | file                                  | note                                                                                                                                                 |
| -------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| claude   | `~/.claude/settings.json`             | replaces the array for each installed event (other tools' hooks on those events are deleted); original saved once as `settings.json.agent-hooks.bak` |
| codex    | `~/.codex/hooks.json`                 | replaces the whole hooks map                                                                                                                         |
| grok     | `~/.grok/hooks/agent-hooks.json`      | replaces the whole hooks map                                                                                                                         |
| gemini   | `~/.gemini/settings.json`             | replaces per event; `timeout` in milliseconds (HEAD only; older binaries wrote seconds)                                                              |
| copilot  | `~/.copilot/hooks/agent-hooks.json`   | compaction installed as PascalCase `PreCompact`                                                                                                      |
| hermes   | `~/.hermes/hooks/agent-hooks.json`    |                                                                                                                                                      |
| opencode | `~/.config/opencode/agent-hooks.json` | nothing reads it; the plugin `~/.config/opencode/plugins/claude-hooks.js` calls `agent-hooks`                                                        |
| mastra   | none                                  | call `agent-hooks UserPromptSubmit` from `processInput` yourself                                                                                     |

`install` creates one entry per native event found in `groups` names or any hook's `events` (hooks for every
`agents` value count, matchers are ignored; cwd `.agent-hooks.toml`/`hooks.toml` are merged in and `--config` is
ignored), whose command is `AGENT_HOOKS_AGENT=<agent> agent-hooks <NativeEvent>`. Its timeout is
`max(default_timeout, slowest hook for that event) + 2` seconds. `install all` runs every harness and fails if any fails. `uninstall` restores the
first backup wholesale (later edits to that file are lost), or strips only entries containing `agent-hooks`.

Not every native event is installable on every harness (`is_native_event`): Claude, Codex, Grok, OpenCode, and
Gemini share the same 11 core events (OpenCode's narrower arm is shadowed by the first); Gemini also gets some
names it does not define (dead entries); Hermes and Copilot have their own lists.

## Event capabilities (what an effect can do)

Claude-shape adapters (Claude, Grok, OpenCode, Mastra): `tool.before` and `permission.request` can deny/ask/allow (encoded in the PreToolUse shape; verify
`permission.request` against a live Claude), and `tool.before` can rewrite tool input;
`turn.stop` and `prompt.submit` can block (Stop block = keep working; UserPromptSubmit block = reject the prompt);
`session.start` and `prompt.submit` accept plaintext stdout as context (Claude, Grok, OpenCode, Mastra, Copilot, Hermes; Codex ignores it; Gemini treats it as invalid); `worktree.create` is special (stdout is
the bare path and exactly one hook may `provides = ["worktree_path"]`); every other event is context-only and
cannot block (`worktree.remove` is blockable). Asking an event to do something it cannot (a deny on `session.start`) makes the dispatcher exit 2
with "unsupported capability".

## Compaction, in one line

Use `context.compact.before` with **no matcher**, for hooks such as `agentmux save-transcript --harness
"$AGENT_HOOKS_HARNESS" --hook-payload`. Claude/Codex/Gemini/Copilot send `trigger`, Grok sends `source`, OpenCode
sends neither, so `manual|auto` silently skips OpenCode. Hermes and Mastra have no compaction event. See
`README.md` in the repo for the evidence per harness.
