# Events and harnesses

Only omp and the Codex desktop app are supported.

Source of truth: `apps/omp/extensions/run-agent-hooks.ts` for omp's emitted events;
`src/events.rs` (`native_event_for`, `normalize_event`) and `src/installer.rs`
(`is_native_event`, install paths) in agent-hooks for the Codex adapter.

## Canonical event to native name

| canonical                  | omp bridge       | Codex adapter                |
| -------------------------- | ---------------- | ---------------------------- |
| `session.start`            | SessionStart     | SessionStart                 |
| `session.end`              | SessionEnd       | SessionEnd                   |
| `prompt.submit`            | UserPromptSubmit | UserPromptSubmit             |
| `tool.before`              | PreToolUse       | PreToolUse                   |
| `tool.after`               | PostToolUse      | PostToolUse                  |
| `turn.stop`                | Stop             | Stop                         |
| `context.compact.before`   | PreCompact       | PreCompact                   |
| `context.compact.after`    | not emitted      | PostCompact                  |
| `subagent.start` / `.stop` | not emitted      | SubagentStart / SubagentStop |

omp also dispatches `PostToolUseFailure` by its native name. Its bridge sets
`AGENT_HOOKS_AGENT=claude` as the binary's required agent-id alias and
`AGENT_HOOKS_HOST=omp`; that alias does not mean a separate harness is supported.

## Wiring

| harness | file                                         | note                                                                          |
| ------- | -------------------------------------------- | ----------------------------------------------------------------------------- |
| omp     | `~/.omp/agent/extensions/run-agent-hooks.ts` | bridge dispatches events directly; do not install a separate settings adapter |
| codex   | `~/.codex/hooks.json`                        | `agent-hooks install codex` replaces the whole hooks map                      |

For Codex, `install` creates one entry per installable native event found in group
names or hook `events`. Hooks for every `agents` value count and matchers are ignored.
Cwd `.agent-hooks.toml`/`hooks.toml` files are merged in and `--config` is ignored.
The generated command is `AGENT_HOOKS_AGENT=codex agent-hooks <NativeEvent>` and its
timeout is `max(default_timeout, slowest hook for that event) + 2` seconds.
`uninstall` restores the first backup wholesale (later edits to that file are lost),
or strips only entries containing `agent-hooks`.

## Event capabilities

omp consumes the binary's shared adapter output: `tool.before` can deny, ask, allow,
or rewrite tool input; `turn.stop` and `prompt.submit` can block. `session.start`
and `prompt.submit` accept plaintext stdout as context. Codex ignores plaintext
context; verify its output schema against the desktop app before relying on deny
or Stop retry semantics (see `known-issues.md`). Other emitted events are
context-only. Asking an event for an unsupported effect makes the dispatcher exit 2
with "unsupported capability".

## Compaction

Use `context.compact.before` with **no matcher**. The omp bridge sends neither
`trigger` nor `source`, so a `manual|auto` matcher silently skips omp. Codex sends
`trigger`.
