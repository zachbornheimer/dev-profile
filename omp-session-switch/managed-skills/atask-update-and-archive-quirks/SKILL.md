---
name: atask-update-and-archive-quirks
description: "Use when editing, archiving, splitting, or adding dependencies to atask tasks and atask update refuses. Captures the exact refusals and the working command shape for each."
---

# atask update / archive semantics

Every refusal below was observed live (capability-replicas, 2026-11-07). Each has one working shape.

## Refusals and fixes

| Refusal | Cause | Fix |
|---|---|---|
| `--title was removed: a task's title is fixed; --archive --reason TEXT it and add the new one` | You tried to retitle | `atask update <id> --archive --reason "..."` in its own call, then `atask add "<new title>" ...`. Record the replacement id in the archive reason. |
| `--archive cannot be combined with other edits; archive in its own update` | Archive passed with `--reason`-plus-anything, including `--project` | One call, nothing but `--archive --reason`: `atask update <id> --archive --reason "..."` |
| `<id> belongs to another project` | You ran from a cwd that resolves to a different project and passed `--project <name>` | `cd` into the project's directory and drop `--project` entirely. |
| `project name "X" is ambiguous; use its id: proj-aaa (no directory), proj-bbb (/path)` | A manual/no-directory project shares the name with the repo project | Use the id, or run from the directory. Prefer the directory. |
| `archiving <A> would leave <B> with a dangling prerequisite; remove that edge` | B `--requires` A | `atask update <B> --remove-requires <A>` first (from the project directory), then archive A. |

## Working shapes

```bash
# from the project directory; no --project needed
cd ~/Developer/Personal/<repo>
atask update <id> --remove-requires <old>      # drop an edge
atask update <id> --archive --reason "..."     # alone, nothing else
atask update <id> --proof "run: cd <claim-worktree>/<sub> && bun test test/x.test.ts size=medium" \
                  --regression "run: cd <claim-worktree>/<sub> && bun test size=large"
```

- `--project` itself counts as "another edit" for archive. Never combine it with `--archive`.
- Every task's proof and regression must point inside that task's claim worktree `~/Developer/Personal/.worktrees/<repo>-atask-<id>`: checks run under Seatbelt denying writes elsewhere.
- `atask add` prints its id at `.result.created["#0"]`, not `.result.id`. Parse that.
- `atask add` warns `outcome contains a conjunction; if it names two independently verifiable results, split the task`. Split into two tasks with `--requires` rather than shipping a compound objective.
- Read state with `ATASK_OUTPUT=json atask list open --project proj-...`, then filter; a bare `atask list` floods.
- Symbol meaning: `○` open, `◐` claimed/in progress, `[blocked]` unmet `requires`.

## See also

`atask context` for the operating contract; this file only records CLI refusal semantics.
