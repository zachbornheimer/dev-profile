# Branch manifest: one file per branch

Use when a build merges more than a handful of topic branches onto a base, and more than one writer (a person, an agent, a generator) adds to the list.

## Why not one list

A single JSON array or JSONL file in the workflow collides: two writers appending at the end conflict on merge, a trailing comma breaks the parse, and a multi-line reason has to be escaped inside a string. Hand-ordering the list also hides the real constraint, which is which branch must merge before which.

## Layout

```text
.omp-build/
  resolve-branches.ts
  branches/
    steering-fixes.toml
    fix/native-build-cargo.toml      # branch fix/native-build-cargo
    local/gateway-rendering.toml
```

The directory name is project-specific; keep it under one directory upstream does not have. The file path under `branches/`, minus `.toml`, is the branch name. There is no `branch` field, so a file and its branch cannot drift. Git refs cannot hold both `a` and `a/b`, and a file and directory cannot either, so the layout cannot represent an impossible set.

## Schema

```toml
reason = "build:native finds cargo without setup, and names what to install if it is missing."
upstream = "candidate" # no | candidate | submitted | merged
pr = "" # required when upstream = "submitted"
layer = 50 # merge order, lower first; default 50
```

- `reason`: plain English, what the branch does for the person running the build. Required.
- `upstream`: `no` = personal, never submitted. `candidate` = suitable for a PR, not yet sent. `submitted` = PR open (needs `pr`). `merged` = upstream has it; delete the file.
- `layer`: order. Resolve by `(layer, path)`, so ties are alphabetical and the result is deterministic. Use a lower layer for a base that others depend on.

TOML because it takes multi-line prose without indentation traps. Bun parses TOML natively as far as I know; confirm against the Bun version the workflow pins before relying on it.

## Resolver checks (fail the run, with the file named)

1. `reason` present and not a TODO.
2. `upstream` is one of the four values; `submitted` has a `pr`.
3. The branch exists on the fork remote.
4. No duplicate resolved branch names.

Warn, do not fail:

- The branch is already an ancestor of `upstream/main`: print "merged upstream, delete this file".
- `upstream = "merged"` but the branch still has commits upstream lacks.

## How writers use it

- Add a branch: create its file. Nothing else changes, so no other writer conflicts.
- Remove one: delete its file.
- Same branch added twice: same path, so git reports a conflict. That is the correct collision.
- Generators write a file per output. If a generator emits dozens of near-identical entries, it is producing something that belongs in a plugin or tools directory, not in branches (SKILL.md section 1).

## Migrating an existing JSON manifest

1. Write the resolver to read the directory, and keep it reading the old JSON until the move is done.
2. Convert entries mechanically: one file per entry, path from `branch`, `reason` copied, `layer` from list position for any entry that must stay ordered.
3. Dry-run the resolver on both formats and compare the resolved branch lists. They must match before the old block is deleted.
4. Remove the JSON block and the old reading code in the same commit. Leave no dual reader.
