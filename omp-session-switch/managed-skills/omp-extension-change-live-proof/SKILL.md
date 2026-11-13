---
name: omp-extension-change-live-proof
description: "Proving an edit to ~/.omp/agent/extensions landed and works when this session's process still holds the old module: fresh headless omp as the live probe, symlink repointing after landing, and the stale-module symptom."
---

# Proving an omp extension change works

## The trap

omp loads each extension module **once, at process start**. Editing
`~/.omp/agent/extensions/<name>/*` and then calling the tool in the *same* session
exercises the old code. The tool answers exactly as before, so a fix looks like it
did nothing.

Symptom seen live: `skill_search` kept returning
`"degraded":true, "reason":"… this host has no judge …"` after
`catalog_judge.ts` was added and the tool source verified by grep.

## Probe a fresh process instead

`omp_restart` is the intended reload, but it forks via Tern and fails with
`tern new: no Tern is running` on a Mac without the daemon. Do not stall on that —
spawn a headless omp, which loads extensions from disk for real:

```js
const omp = "<absolute path to the omp binary>";           // e.g. the newest
                                                            // ~/.local/share/mise/installs/github-*/build-*/omp
const prompt = `Call the <tool> tool exactly once with {…}. Then answer with exactly one line: ` +
               `DEGRADED=<true|false> REASON=<reason> IDS=<count>`;
Bun.spawn([omp, "-p", prompt, "--tools", "<tool>"],
  { cwd: "/tmp", stdout: Bun.file("/tmp/probe.out"), stderr: Bun.file("/tmp/probe.err") });
```

Facts that make this cheap and reliable:

- `--tools <tool>` allowlists, so the child only exercises the changed surface.
- Startup takes 30–60 s (`createAgentSession > loadCustomTools`); poll the out file
  inside one `eval` cell rather than a shell sleep loop, which `run_command` refuses.
- Ask the child for a **single fixed line**. Anything longer and you cannot tell a
  pass from a partial answer.
- The verdict is the tool's own fields (`degraded`, `reason`, counts). A test suite
  going green proves the code; only the fresh process proves the *host* wiring.

## Symlinks between extension dir and repo

`~/.omp/agent/extensions/<name>` is often a symlink into the repo. If the edit was
made in a worktree, the symlink points at that worktree, and pruning it later
breaks every extension import. After the change lands on `main`, repoint:

```sh
ln -sfn /Users/zbornheimer/Developer/Personal/<repo>/<path-to-extension> \
        /Users/zbornheimer/.omp/agent/extensions/<name>
readlink ~/.omp/agent/extensions/<name>   # confirm
```

Check the file lands where the symlink now points (`test -f <target>/<new-file>.ts`)
before claiming the live extension carries the fix.

## Related: pre-commit hooks that shell out to `mise x`

A repo whose `.pre-commit-config.yaml` uses `mise x hk …` can hang indefinitely in
a non-interactive agent shell: `mise x` stalls there, the hook never prints, and
every commit attempt times out. Diagnosis, in this order:

1. Read what the hook actually runs.
2. Run the same gate commands with the `hk` binary directly
   (`hk run pre-commit --staged <stages>`). Green output there is the real gate.
3. Only with those gates green, commit with `HK=0` and say so in the report — and
   mention the `mise x` stall as the reason, so nobody reads it as a bypass.

Prefer `mise run <task>` when the repo exposes the gate as a task; the stall is in
`mise x`, not in mise itself.
