---
name: agent-hooks
description: >-
  Operate the agent-hooks dispatcher (~/Developer/Personal/agent-hooks): one hooks.toml catalog
  (~/.config/agent-hooks/hooks.toml, chezmoi-managed) that runs guards and gates for Claude Code, Codex, Gemini,
  Grok, Hermes, Copilot, OpenCode, and Mastra. Use whenever the user adds, changes, reorders, tests, installs,
  or debugs a hook, guard, or gate: PreToolUse deny/ask/rewrite, PostToolUse, Stop (completion-gate, "stop the
  agent ending turns / asking permission"), UserPromptSubmit context, SessionStart, PreCompact, WorktreeCreate;
  scripts under ~/.agents/hooks; `agent-hooks validate|list|doctor|install`; hooks.log; or a hook that "did not
  fire", "fired twice", "blocked with the wrong reason", "failed open", "panicked / exit 101", or "reverted after
  chezmoi apply". Also use when a hook calls TypeSafe (judge-turn) or someone wants to merge
  TypeSafe checks. NOT for git hooks (husky, lefthook, pre-commit, zq), worktrunk `wt` hooks or "a hook denied
  my git command, what is the allowed alternative" (worktrunk-index), third-party plugins that install their own
  hooks (Hindsight, AOE), React hooks, webhooks, or TypeSafe question design and threshold tuning
  (typesafe-ai-effective-use).
---

# agent-hooks

`agent-hooks <SELECTOR...>` is the one command every harness's native hook entry calls. It reads the harness's
event JSON on stdin, runs every matching hook from one TOML catalog **concurrently**, merges the results, and
prints one native response. Adapters own each harness's quirks.

Repo `~/Developer/Personal/agent-hooks`: `README.md` and `docs/adr/0001-dispatcher.md` describe it (`SPEC.md` is
a stub); `LAYOUT.md` is the module map. Catalog: `~/.config/agent-hooks/hooks.toml`. Scripts: `~/.agents/hooks/`.
Both are **chezmoi-managed**.

| If the task is                                                 | Go to                                                     |
| -------------------------------------------------------------- | --------------------------------------------------------- |
| a hook did not fire / fired twice / wrong reason / failed open | Debugging                                                 |
| add or change a hook                                           | Add or change a hook (steps 1-7)                          |
| what JSON to return, per harness                               | Output shape per harness                                  |
| matcher, selector, agent filtering                             | Mental model, Matching                                    |
| a TypeSafe call inside a hook                                  | TypeSafe in hooks, then `references/typesafe-batching.md` |
| harness event names, install paths                             | `references/events-and-harnesses.md`                      |
| known live defects (dated)                                     | `references/known-issues.md`                              |

## Mental model

1. **The catalog is the source of truth; harness config is generated.** `agent-hooks install <agent|all>` writes
   one entry per native event (`AGENT_HOOKS_AGENT=claude agent-hooks PreToolUse`, timeout = max(`default_timeout`,
   slowest hook for that event) + 2 s). A new hook on an event the harness already calls needs no re-install.
2. **Selector = group name, then hook name, then event name** (canonical or native: `tool.before` = `PreToolUse`).
   The event that runs comes from the **payload**, not the selector: selecting `PostToolUse` with a PreToolUse
   payload runs nothing. A group named like an event shadows event selection. Unknown selectors and events with no
   hooks warn "skipping unknown selector" and exit 0. A hook with empty `events` runs when named, never by event.
3. **Hooks are independent parallel processes** (bounded by `max_concurrency`). They share nothing; event wall time
   is the slowest hook. Work several hooks need (a model call, a transcript parse) is repeated per hook.
4. **Fail-open is the default.** Crashes, bad output, and timeouts warn and the action proceeds. Never assume a
   guard guards until you have seen it deny.

## Add or change a hook (in order)

```toml
[[hooks]]
name = "pretooluse-my-guard" # unique; a same-name row silently REPLACES an earlier one
events = ["tool.before"]
command = ["/Users/zbornheimer/.agents/hooks/my-guard.py"]
matcher = "Bash|bash" # exact, case-sensitive names (see Matching)
timeout = "10s" # humantime; default 30s
on_failure = "warn" # ignore | warn (default) | block  (read "Blast radius" before block)
protocol = "native" # native (default) | common
agents = ["claude", "codex"] # empty = all
env = { MY_FLAG = "1" }
```

1. **Write the script** with the house runner (stdin, logging, fail-open). Copy the structure of
   `~/.agents/hooks/process-kill-guard.py` (the pattern, not a live guard: its catalog row is a command-less stub)
   and test with `~/.agents/hooks/tests/hook_harness.py`:

   ```python
   #!/usr/bin/env -S uv run --script
   # /// script
   # requires-python = ">=3.10"
   # dependencies = []
   # ///
   import sys
   from pathlib import Path

   sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
   from command_words import (
       simple_commands,
   )  # parse the command; do not substring-match it
   from hook_common import Decision, HookEvent, run_hook


   def is_bad(argv: list[str]) -> bool: ...  # your rule, on one parsed argv
   def decide(event: HookEvent) -> Decision | None:
       if event.tool_name != "Bash":
           return None
       for argv in simple_commands(event.tool_input("command") or ""):
           if is_bad(argv):
               return Decision.deny("what you did, what to do instead")
       return Decision.no_objection(
           "my-guard:ok"
       )  # logs a line; returning None logs nothing


   if __name__ == "__main__":
       run_hook("my-guard", decide)
   ```

   `Decision` has `deny`, `allow` (optional `updated_input`), `block` (Stop), `context(text, event_name)`,
   `no_objection`. All emit **Claude-shaped** JSON. `run_hook` is **always fail-open**: an exception inside `decide`
   is logged `fail-open:` and exits 0, so a guard that must not fail open wraps its logic in `try/except` and returns
   `Decision.deny(...)` itself. The script must live in `~/.agents/hooks/` for the `lib` path to resolve.
2. Add the catalog row. Time the script with `~/.agents/hooks/suggested-timeout-for.py --payload event.json -- <script>`
   (needs `hyperfine`; the default payload `{}` hits the early-return path; `ceil(p95)` has no headroom). Native
   timeouts fail open, so leave margin.
3. **Validate, then audit**: `agent-hooks validate` (schema, version, agents, durations, group cycles, name
   clashes, duplicate exclusive `provides`), then `~/.agents/available-skills/agent-hooks/scripts/audit-catalog.py
   [file]` for what `validate` accepts silently (see "What validate misses").
4. **Dry-run both paths with a real payload**, isolating state so tests do not write the live log. Select your hook
   **by catalog name** (`... hooks.toml pretooluse-my-guard`); selecting `tool.before` also runs every live guard
   (e.g. `bash-tool-steer` denies Bash itself), which can look like your guard working:

   ```bash
   HC_STATE_DIR_OVERRIDE=$(mktemp -d) sh -c 'echo "{\"session_id\":\"s\",\"cwd\":\"/tmp\",\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git push --force\"}}" \
     | agent-hooks --agent claude --config hooks.toml pretooluse-my-guard 2>&1; echo rc=$?'
   ```

   A denial prints `{"hookSpecificOutput":{"permissionDecision":"deny",...}}` and exits **0**: that is the protocol.
   Allow and never-matched are both silent; tell them apart with `no_objection` log lines or a canary hook (same
   `events`/`matcher`, writes stdin to `/tmp`).
5. `agent-hooks install <agent>` only if the event is new to that harness or a timeout grew. **Install replaces the
   whole array for every event it writes**, deleting other tools' hooks on those events in that harness file (the
   live Claude file has AOE entries on SessionStart/UserPromptSubmit); it also rewrites the JSON with sorted keys.
   It merges `./.agent-hooks.toml`/`./hooks.toml` from the cwd and ignores `--config` (use
   `AGENT_HOOKS_CONFIG=file agent-hooks install ...`). Preview safely: `T=$(mktemp -d); mkdir -p $T/.claude; cp ~/.claude/settings.json $T/.claude/; cd $T; HOME=$T
   AGENT_HOOKS_CONFIG=~/.config/agent-hooks/hooks.toml agent-hooks install claude`, then diff against the copy.
   `uninstall` restores the first backup (`*.agent-hooks.bak`) wholesale; later edits to that file are lost.
6. **Persist.** `chezmoi re-add ~/.config/agent-hooks ~/.agents/hooks` (`chezmoi add` for a new script; source names
   use `dot_`/`executable_`). An unre-added live edit is silently reverted by the next `chezmoi apply`. Check with
   `chezmoi status ~/.agents/hooks ~/.config/agent-hooks` and `chezmoi re-add -n -v <paths>`. (`chezmoi-guard.py
   --check` is currently broken; see known-issues.)
7. Prove it live in the harness on one real event, then read its log line.

**Blast radius.** With the house runner, `on_failure="block"` fires only when the script cannot start (bad import,
missing `uv`), and then it blocks **every** matching call, including the one you need to fix it. Use it only with a
narrow matcher and an env bypass the script checks first. Otherwise fail closed inside the script (step 1).

## Config loading and command forms

`--config FILE` (beats `AGENT_HOOKS_CONFIG`) loads that file alone. Otherwise: user file, then `./.agent-hooks.toml`,
then `./hooks.toml` from the cwd (any project with a `hooks.toml` gets it merged in). A later same-name hook replaces
the earlier one in place. `[defaults]` (agents, protocol, shell, timeout, on_failure) applies per file.

- `shell = true` (live `[defaults]`; code default is false): `command[0]` runs under `/bin/sh -c`; extra items become
  `$0`, `$1`, so they are **not** passed as arguments (put arguments inside the string). **Never `["sh","-c","..."]` here** (becomes `sh -c sh -c ...`; the live `stop-payload-dump-tmp` is
  broken this way). Put the whole command in element 0.
- `shell = false`: literal argv, no `~`/`$HOME` expansion; a single string that is a command plus arguments is one
  program name and fails to spawn (a path that happens to contain spaces is fine).
- Child env: `AGENT_HOOKS_AGENT`, `AGENT_HOOKS_HARNESS` (e.g. `claude-code`), inherited env, and `env`.
- Limits: stdin 8 MiB, each of stdout/stderr 1 MiB.

## Output shape per harness (not "write once")

`protocol = "native"` means **each harness's own JSON**. "Claude-shape" = Claude, Grok, OpenCode, Mastra. Others
differ (verified in the adapters): Copilot has its own adapter (deny is flat `{"permissionDecision":...}`, context
dropped on deny); Gemini ignores `hookSpecificOutput.permissionDecision` (needs top-level
`{"decision":"deny","reason":...}`); Hermes understands only `{"decision":"block"}` and `{"context":...}`; Codex's
encoding of deny and Stop-block does not match Codex's published output schema (upstream schema checked, no live
Codex run) and drops the nested reason; verify on a live Codex. House scripts and `hook_common` speak Claude-shape. For identical behavior everywhere use
`protocol = "common"`: stdin is normalized (`version`, `agent`, `event`, `native_event`, `session.id`, `cwd`,
`context`, `data`, `raw`) and stdout is `{"effect": "none|allow|ask|deny|retry|halt", "reason",
"additional_context", "system_message", "replacement": {"tool_input": ...}}`. Common quirks: empty or non-JSON
stdout is an invalid-output failure; the exit code is ignored.

| Goal (Claude-shape)           | How                                                                                                                                                                                 |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| deny a tool / reject a prompt | `permissionDecision:"deny"` + reason, or exit 2 + stderr (exit 2 only works on `tool.before`, `permission.request`, `prompt.submit`, `turn.stop`)                                   |
| keep Stop from ending         | `{"decision":"block","reason":...}` or exit 2                                                                                                                                       |
| ask the user                  | `permissionDecision:"ask"` (no-op on `prompt.submit`)                                                                                                                               |
| add context                   | `hookSpecificOutput.additionalContext`; plain stdout also counts on SessionStart/UserPromptSubmit for Claude-shape, Copilot, Hermes (Codex ignores it; Gemini treats it as invalid) |
| rewrite tool input            | `hookSpecificOutput.updatedInput`                                                                                                                                                   |

`halt` and `{"continue":false}` do **not** stop the run on Claude or Codex: on Stop they become a block, on
PreToolUse/UserPromptSubmit they are dropped, on PostToolUse/SessionStart the dispatcher errors. Use deny/retry.
Exit 2 on a non-blocking event makes the dispatcher exit 2 ("unsupported capability") and loses the reason.
`additionalContext` is capped at 10 000 bytes (Claude-shape and Copilot); a multibyte character on that boundary
panics the dispatcher (exit 101), so keep context far below it (`references/known-issues.md`).
Per-event capabilities and non-Claude event names: `references/events-and-harnesses.md`.

## Matching

- `matcher` is an **exact, case-sensitive name list** split on `|` or `,`: not a regex (`Ba.*`, `Bash*` never
  match). Tested against the tool name and the payload's `source`, `trigger`, `notification_type`, `agent_type`,
  `compact_trigger`. `""` and `*` match all. Prompt text is never matched.
- Events with none of those fields (Stop, plain UserPromptSubmit) never match a non-empty matcher; omit it there.
  Compaction hooks omit it too because OpenCode sends no `trigger`.
- Tool names differ per harness (`Bash`, `bash`, `run_command`, `mcp__...`); list each spelling a guard must cover:
  `bash-tool-steer` uses `Bash|bash|sh|zsh|shell|terminal|exec|run_terminal_cmd|run_terminal_command`. Hermes renames
  only `terminal`, `write_file`, `patch`, `delegate_task` to Bash/Write/Edit/Task.
- `agents` filters by harness. Detection: `--agent`, `AGENT_HOOKS_AGENT`, Grok env, one matching harness env var,
  then payload shape; ambiguity is an error (exit 2).

## Failure and aggregation (verified by experiment)

| Situation                                                                      | Result                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| native hook times out                                                          | killed, warning; **action proceeds even with `on_failure="block"`**                                                                                                                                                                             |
| `common` hook times out or prints nothing                                      | invalid-output failure: **blocks** under `on_failure="block"`                                                                                                                                                                                   |
| native non-zero exit (not 2), no JSON on stdout                                | failure: `warn` proceeds, `ignore` silent, `block` blocks (blockable events)                                                                                                                                                                    |
| native hook killed by a signal                                                 | silent pass, even under `block` (no exit code)                                                                                                                                                                                                  |
| native exit 0, non-JSON stdout                                                 | Claude-shape/Copilot/Hermes: ignored (injected as context on SessionStart/UserPromptSubmit); Codex: ignored; **Gemini: invalid-output failure, blocks under `block`**                                                                           |
| native JSON plus exit 1                                                        | JSON wins; exit 2 still forces at least a deny                                                                                                                                                                                                  |
| failing hook with `block` on a non-blockable event (PostToolUse, SessionStart) | dispatcher errors, exit 2                                                                                                                                                                                                                       |
| several hooks deny                                                             | strongest effect wins (deny > ask > allow); the **reason comes from the first hook in plan order that has any reason**, even a failing hook's stderr, an allow/ask reason, or an empty string; contexts and system messages from all are joined |
| two hooks return `updatedInput`                                                | objects deep-merge; a conflicting key exits 2. `provides` is only a validate-time declaration                                                                                                                                                   |
| Hermes: exit 1, garbage, or timeout with `block`                               | allowed (only exit 2 blocks)                                                                                                                                                                                                                    |

Plan order is the selector's expansion order: config order for event selectors, member order for groups. Put the most
actionable denier first, give every blocking hook a self-contained reason, and never rely on a timeout to stop
anything.

## What validate misses

`validate` rejects bad schema, agents, durations, group cycles, and name clashes, but `validate`, `doctor`, and `list`
do not catch: unknown keys (`matchr`, `on_failur`, `enabled`, `async`, `priority`,
`filter`, `script`, `policy` are all ignored; `enabled=false` still fires), event-name typos, duplicate names
(replaced silently), or a row with no `command` (skipped: **a `policy=`/`script=` row with no `command` never
runs**). `list` prints only `name (Some(Native))`. Run `scripts/audit-catalog.py [file]`: it flags all of these plus
regex-looking or never-matching matchers, `[shell, "-c", ...]` and stray arguments under `shell=true`, `~`/`$HOME`
under `shell=false`, missing or non-executable scripts, and unknown agents. It audits one file.

## Debugging (stop at the first step that explains it)

0. **Evidence first.** `tail -f ~/.agents/hooks/state/hooks.log` while triggering the event (grep the **script**
   name such as `bash-tool-steer`, not the catalog row name). Lines: `<iso>\t<hook>\t<decision>\t<detail>`; a native
   timeout shows as `fail-open: cancelled (SIGTERM)`. **No line is ambiguous**: not selected, or the script
   returned `None`/bailed early, or it is not a house-runner script, or the log rotated (5 MB to `hooks.log.1`).
   The dispatcher's own warnings go to stderr, which the harness hides; for non-house hooks run the dispatcher by
   hand with `2>&1`. Stop judgments: `completion-gate-judgments.jsonl` (`path`, `fallback_reason`, `signals`).
1. Did the harness call the dispatcher? Look at its generated config for that event.
2. Run `audit-catalog.py`: command-less stub, regex matcher, event typo, duplicate name, shell/array misuse.
3. Matcher exactness against the payload's real field (tool name, `source`, `trigger`).
4. `agents` and agent detection (wrong agent changes filtering and output shape).
5. Fired twice: two entries (harness-native plus dispatcher, or user file plus `./hooks.toml`), or overlapping events.
6. Odd block reason: an earlier hook in plan order supplied it.
7. Failed open: native timeout, `warn` default, exit-0 garbage, signal death, `run_hook` swallowing an exception.
8. Exit 101 from the dispatcher is a Rust panic (context cap), not a hook failure.
9. Behavior differs from the source: the binary on PATH may be stale. `agent-hooks --version` has no commit, so
   compare `which -a agent-hooks` (mise shim and `~/.cargo/bin`) file mtimes with `git log -1 --format=%cd`;
   `cargo build` does not update `~/.cargo/bin`, use `cargo install --path ~/Developer/Personal/agent-hooks`.

## TypeSafe in hooks

The dispatcher has no ordering field (`HookSpec` has no `after`/`stage`), and parallel hooks share nothing, so
"one request, then parallel follow-ups" must live **inside one owner hook per (event, state)**:

1. Prefilter in code; return early without a request.
2. **Wave 1: one request** holding every question about the shared primary state (namespaced ids). Decide in code.
3. **Wave 2: parallel requests** (threads, one total deadline) only for follow-ups that need a different state or
   are conditional on wave 1. Independent and cheap ones start with wave 1.
4. Merge in code: one reason naming every failed rule; one log row.

Two separate hooks calling TypeSafe give two requests, two verdicts, and one surfaced reason (the first in plan
order), and the second cannot wait for the first. Fail open on any TypeSafe error and log why; budget one deadline
across the up-to-three-hop fallback chain; replay and shadow-test before changing a shared request.
Placement rules, the Stop and UserPromptSubmit inventories, keys, logging:
`references/typesafe-batching.md`. Question wording, primitives, thresholds: `typesafe-ai-effective-use`.

## Developing agent-hooks itself

Rust 2024; modules per `LAYOUT.md` (`adapters/*` protocol, `resolver`, `executor`, `aggregator`, `installer`).
`cargo test`; `tests/acceptance.rs` drives the real binary with `hook-fixture` (`--stdout --exit --sleep-ms
--record`). New harness behavior = adapter change plus an acceptance test. Dated defects: `references/known-issues.md`.
