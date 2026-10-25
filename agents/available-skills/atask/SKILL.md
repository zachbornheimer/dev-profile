---
name: atask
description: >-
  Decide whether a finding is a new atask objective, then file it with a real
  --proof and --regression. Use when the user is asking for something to be done that can be verified,
  use when fixing bugs, reviewing spec, analyzing reviews, audits, chats, diffs,
  or docs and turning them into board items; when a prompt, handoff, or reference doc says to load
  atask; when the user asks to add, split, or skip a task. Does not implement
  or claim. Linear stays tickets; Gas City city-internal stays gc bd.
---

# atask — file objectives

atask is the durable board for **independently verifiable outcomes**. Loading
this skill **authorizes filing** (inspect board → add/update). It does **not**
authorize implementation, claim, or `verify complete`.

Canonical path (paste this into prompts and handoffs):

```text
~/.agents/available-skills/atask/SKILL.md
```

Deeper tables: `references/when.md`. CLI shapes: `references/file.md`.
Paste-ready embed blocks: `references/embed.md`.

## First moves

```bash
atask list --json
atask show ID          # only for likely duplicates
atask help add         # if the installed binary's flags are unknown
```

`--project NAME` is the only project selector (default `general`, which holds
tasks filed outside a registered repo). `atask list [all|open|ready|blocked|draft|complete|archived]`
takes no positional project. Repo work: `atask init` already done, or pass
`--project`. `ATASK_OUTPUT=json` when parsing.

`--project` may repeat on `add` and `update`; the first is the home. The home decides the task's repo, worktree and target branch, and is fixed after the first claim. Later projects are memberships: `atask list --project X` includes every task naming X. JSON has `project` (home) and `projects` (ordered). `--requires` needs one shared project.

Stale `atask` on PATH is common. Prefer `$(mise which atask)` or a worktree
build. Do not invent verbs (`ready`, `comment`, `whoami`).

## File or skip

| File                                                     | Skip / reuse                                                          |
| -------------------------------------------------------- | --------------------------------------------------------------------- |
| One cohesive outcome a later worker can prove            | A step toward an outcome (`write the test`, `open the PR`)            |
| Distinct shippable results (split)                       | Same open title already on the board (second `add` returns that id)   |
| Review/audit finding that is real, not already in code   | Already implemented — log on the existing task or leave it            |
| Follow-up discovered while analyzing, with its own proof | Gas City city-internal (`gc bd`) or a Linear ticket (`tickets` skill) |

Conjunction in the title (`and` / two verbs that each verify) → **two tasks**,
or one task only if a single check proves the combined outcome.

Epic/`--group` only when children share one delivery or aggregate check.
Independent siblings stay independent. `--requires` only for a real
prerequisite, not list order.

## How to add

Every task declares two proofs, neither run at add time:

- `--proof "PRESET: SUBJECT [k=v]"` proves this task works (small, 30 s, unless `size=` is set).
- `--regression "PRESET: SUBJECT [k=v]"` proves nothing else broke. Its budget is
  the check option `size=small|medium|large|eternal` (30/300/900 s/no budget); omitted, the preset's default size.

A task missing either is a **draft** (`◌`): listed under `atask list draft`,
never claimable. `atask update ID` with both proofs readies it. File a draft
only when asked to park an idea whose proof cannot be named yet — that is rare;
the default is to file the objective with its proof or not file it at all.
Never claim a draft.

The proof is **one obvious command** against a named surface that already
exists or that this task's own scope creates: `go_test` one package with
`name=`, `js_test`/`py_test` one file named basically like the task,
`playwright_run` one spec named like the task, `run` one targeted
`mise run test:<area>` or one section's suite. If the only way to verify the
objective is a bespoke throwaway script, the task is mis-scoped: rescope or
split until the proof is that single command. When the expedient test surface
is missing, creating that named surface is part of the task's outcome, and the
proof names it. Never file a placeholder or a "write a script to verify" proof.

```bash
atask add "Reject invalid session with the specified response" \
  --outcome "Invalid session is rejected; valid login still succeeds" \
  --accept "Invalid session rejected" \
  --accept "Valid login succeeds" \
  --proof "go_test: ./internal/auth name=TestRejectInvalidSession" \
  --regression "go_test: ./internal/auth size=medium" \
  --requires at-xxxxxx
```

Presets (`atask help add` lists all with default sizes):

| Preset                                                | Subject / options                     |
| ----------------------------------------------------- | ------------------------------------- |
| `run`                                                 | `COMMAND [expect=REGEX]`, raw command |
| `ci`, `lint`, `build`                                 | none; `mise run X`, else `make X`     |
| `go_test`                                             | `PKG [name=REGEX]`                    |
| `py_test`, `js_test`, `rs_test`                       | `PATH [name=..]`                      |
| `pl_test` `php_test` `rb_test` `swift_test` `sh_test` | `PATH [name=.. expect=..]`            |
| `playwright_run`                                      | `SPEC [grep=REGEX project=NAME]`      |
| `file_exists`                                         | `PATH`                                |
| `file_absent`                                         | `GLOB [depth=N]`                      |
| `file_blake3`                                         | `PATH hash=HEX`                       |
| `grep`                                                | `PATH pattern=REGEX [absent=true]`    |
| `http_ok`                                             | `URL [status=CODE body=REGEX]`        |
| `pr_merged`                                           | `NUMBER\|URL`                         |

Rejected at add (vacuity): `run: true` and other no-ops, no encoded payloads in
`run` args, and a small `go_test` on a whole tree without `name=` (narrow it or
use `size=medium` or `size=large`). A `*_test` that runs zero tests fails at verify.

Post-completion actions: `--on-complete "PRESET: ..."` (waited, 900 s) or
`--on-complete-detach "PRESET: ..."` (not waited on).

Many items: `atask add -f plan.yaml` (atomic). Reuse an existing id: `atask
update ID` for contract fields. Soft-cancel: `atask update ID --archive --reason "…"`.

After filing, report **real ids** from `atask show` / `atask list --json`. A
prose checklist is not a board.

## Autonomy

When this skill is on the worker (prompt, handoff, or “load atask”):

1. Inspect the live board in the right project/unscoped cwd.
2. Analyze the given material (review, diff, doc, transcript).
3. File every missing **outcome** that meets the table above.
4. Skip duplicates; update a deficient proof rather than cloning.
5. Stop. Do not claim, edit product code, or spawn implementers unless the
   caller separately authorized that.

## Gotchas

- `run` executes argv without a shell: use `sh -c` only for shell syntax.
- Small unbounded `go_test` (no `name=`) is rejected at add; that is not a
  parse/syntax error.
- Duplicate open titles collapse to the oldest live id.
- Diagnostics (workers, not filers): `atask verify proof|regression|complete`;
  `claim release --failed` counts an attempt, plain `claim release` does not.
- Do not run `atask project`. Humans configure target branch and attempts.
  A project holds no checks; agents put both proofs on the task.
