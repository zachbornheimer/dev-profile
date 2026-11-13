---
name: omp-file-edit-extension
description: "Working on or debugging ~/.omp/agent/extensions/file-edit (edit/edit_patch/edit_replace/write, locks, journal, /cwd, /allow-unscoped-writes, foreign-worktree guard) or ~/.omp/agent/tools/run_command worktree guards, or diagnosing omp \"Failed to load extension\" / \"Custom tool load failed\" / agent parse errors in ~/.omp/logs"
---

# file-edit extension, worktree ownership guards, and omp load-error gotchas

**Where**: `~/.omp/agent/extensions/file-edit/`. It owns `edit`, `edit_patch`, `edit_replace`, `write`, `/cwd` and `/allow-unscoped-writes`. `zab-ai-tools` no longer registers any of them (capability-replicas commit `ad6303e023`).

**Self-contained rule**: sources import only relative `.ts` files, `node:*` and `bun:*`. No `@zab-ai`, no `capability-replicas`, no symlinks. `engine/engine_guard.test.ts` enforces it for `engine/`.

**Load order**: omp binds extensions in path order and a same-name tool registration is last-wins. An extension that sorts later (for example `zab-ai-tools` after `file-edit`) silently overrides the earlier one. Check `/tool-sources` before assuming a new tool is active.

**Worktree auto-fork and foreign-worktree ownership (`fork.ts` + `tools/run_command`)**:
- `routeTargets` runs in all 4 tools (`edit`, `edit_patch`, `edit_replace`, `write`). It auto-forks both when `sessionCwd` is inside a `main`/`master` primary checkout AND when a session targets any real git repo's primary checkout from an external `cwd` (provided `sessionCwd` is not already a linked worktree of that repo).
- `mainCheckoutOf` (`fork.ts`) and `assertEditable` (`engine/resolve.ts`) recognize any primary checkout (`.git` is a directory) whose parent directory has a `.worktrees` sibling (such as `~/Developer/Personal/<repo>` or `~/Developer/Software-Automation-Holdings/<repo>`), even if someone accidentally switched `.git/HEAD` off `main`/`master`.
- `assertWorktreeOwnership` (`fork.ts`) refuses any `edit`, `edit_patch`, `edit_replace` or `write` targeting a linked worktree (`.git` file pointing to `.git/worktrees/<name>`) unless: (1) `/allow-unscoped-writes on` is granted, (2) `sessionCwd` is inside that worktree, (3) `.omp-isolation-owner.json` sits in its parent dir, (4) the worktree/branch ends with this session's 8-hex prefix, (5) the worktree is in `~/.omp/agent/forks/<session>.json`, or (6) the worktree was recorded in `~/.omp/agent/forks/*.json` with an `ownerPid` in this process's ancestry.
- `tools/run_command/worktree.ts` refuses raw `git switch`, `git switch -c`, `git checkout -b`/`-B`/`--orphan`, `git checkout <branch>`, and `gh pr checkout` before spawn (steering to `wt switch` / `wt switch -c`). `tools/run_command/host_policy.ts` (`worktreeOwnershipRefusal`) refuses mutating `git` and `wt` commands inside foreign linked worktrees and `wt switch <existing-foreign-branch>` without `-c`, and `recordWtCreatedWorktrees` records any worktree newly created by `wt switch -c` / `wt tree-for-changes` into `~/.omp/agent/forks/<session>.json` with `ownerPid: process.pid`.

**Concurrency design**:
- `lock.ts` takes a file-creation lock per canonical path. A dead holder pid is stolen from, locks over 120s are stolen, and a live holder refuses the call after a 20s wait.
- `guard.ts` journals every change (before tag, after tag, op, intent, diff). A stale-tag edit, or a `write` over a file changed since the session last read it (tags come from `[path#TAG]` headers in `read` and `grep` results), is refused with the other agent's change in the message.
- `changesSince` must match a seen tag against both journal `after` and the first entry's `before`, or a file nobody edited yet reports "changed some other way".

**State and test isolation env vars**: `OMP_FILE_EDIT_STATE` (locks and journal, default `~/.local/state/omp-file-edit`), `OMP_FILE_EDIT_LOCK_WAIT_MS`, `OMP_FORKS_DIR`, `OMP_EDIT_REGISTERS_DIR`, `UNSCOPED_WRITES_DIR`.

**Verify**:
- Tests: `cd ~/.omp/agent/extensions/file-edit && bun test` and `cd ~/.omp/agent/tools/run_command && bun test worktree_verbs.test.ts`.
- Load only this extension in real omp: `omp --no-extensions -e ~/.omp/agent/extensions/file-edit/index.ts -p "..."`, then `tail` the journal.
- Do not run vitest in capability-replicas (a user rule forbids it); use `bun build <entry> --target=bun --external '@oh-my-pi/*'` instead.
- A standalone bun script cannot import oh-my-pi's `discoverAndLoadExtensions` (the checkout has a broken tui theme import), so test through real `omp -p`.

**Machine gotcha**: this Mac often runs at load average 100+ (472 seen). Commands then time out and a full `omp -p` start can exceed 250s. Run test suites and commits in the background with output redirected to a log file, then read the log.

**Finding load errors**: omp logs JSONL to `~/.omp/logs/omp.<date>.<pid>.log`; grep it for `"level":"error"` and `Failed to load extension`, `Custom tool load failed`, `Failed to read agent file`.

**Resolved load errors (2026-11-11)**:
- A custom tool may not reuse a builtin name. The custom `recall` collided with the builtin `recall` and was renamed `rank_recorded_context` (`~/.omp/agent/tools/rank_recorded_context/`).
- `~/.omp/agent/agents/code-implementer.md` had a corrupted first line (`ame:`, no `name`) while `render.py` was correct. Re-run `python3 ~/.agents/agents/render.py <name>` (`--check` reports stale) for any generated agent that fails to parse.
- `zab-ai-tools` is a real directory with vendored `kit/` and `runtime/` trees, no symlink and no `@zab-ai` import. The `capability-replicas` strings left under `~/.omp/agent` are data paths (`~/.local/share/capability-replicas/...`) and the stored entry type `capability-replicas.pending-decisions`; they are on-disk identifiers, so leave them.

**Vendored zab-ai-tools data files**: `zab-ai-tools/kit/decisions/questions/ask_gate.yaml` is read when the extension loads, so a missing copy fails the whole extension (`ENOENT` in the omp log) and every tool it registers disappears from fresh sessions, while already-running sessions look fine. `kit/tools/web/summarize.yaml` is read lazily. Source of truth is `capability-replicas/packages/ai/src/`. After vendoring or moving code, check a fresh session's log for `Failed to load extension`, or import `zab-ai-tools/index.ts` under `bun` with a stub `pi` (zod from its own `node_modules`) and list the registered tool names (expect 16 tools plus the `tool-sources` command; `run_command` is a custom tool under `~/.omp/agent/tools/run_command`, not registered here). Prefer the stub check when load is high.
