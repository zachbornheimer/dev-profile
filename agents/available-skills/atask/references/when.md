# When a finding is a task

Read `SKILL.md` first. This file is the decision table.

## Unit of work

A task is one **outcome**: a state that can be true or false after work, proven
by a named proof. It is not a paragraph, a review bullet, a commit, or a
feeling that “someone should look at this.”

| Input                                                      | Task count                        |
| ---------------------------------------------------------- | --------------------------------- |
| One independently deliverable outcome                      | 1, no group                       |
| Two unrelated outcomes                                     | 2, no group required              |
| Two+ changes that need one combined acceptance or delivery | 1 group + the minimum children    |
| One finding, several independent proofs                    | several tasks                     |
| Several findings, one cohesive change                      | 1 task                            |
| Already true on the target                                 | 0 new tasks; reuse / verify later |
| Ordered list with no real dependency                       | parallel tasks, no `--requires`   |

## File

- The user asked to track it, or this skill is loaded against material to mine.
- A later worker could claim it and know done from the proof alone.
- The outcome is not already an open task with the same title or the same
  proof (inspect `atask list` / `atask show`).

## Do not file

- Implementation steps (“add the flag”, “run gofmt”, “open a PR”).
- Process (“write a plan”, “investigate”, “consider”). Investigation is a task
  only if the outcome is a named artifact plus a check that the artifact
  exists **and** answers the question.
- Linear product bugs the user wants in Linear (`tickets` skill).
- Work the user forbade (`do not implement`, `audit only`) — unless they
  asked to **file** it.
- A second task that only exists to remind someone to `verify complete`.

## Split signal

Split when describing the work needs “and” between two proofs that can ship
separately. Keep together when splitting would force two workers to edit the
same invariant or the same check.

## Groups

Use `--group` when there is a shared deliverable or an epic check that runs
once members are complete. A group is not a Git branch by default.

## Dependencies

`--requires ID` means B is not claimable until A is **complete**. If B needs
A’s code in its worktree, completion of A may not be enough (integration
pending). Do not encode “appeared earlier in the review” as `--requires`.

## Proofs that count

`--proof` must be able to fail on the bug and pass after the fix (or, for
research/ops, fail if the claimed artifact is missing or wrong).
`--regression` guards what else could break (`go_test` on the package, `lint`,
`ci`).

Forbidden: `run: true`, a whole-tree small `go_test` without `name=`, encoded
payloads, bare `file_exists` as the only proof of behavior. A project holds no
checks; both proofs live on the task.

No proof yet: file a draft (`atask add "title"` with neither proof), then
`atask update ID --proof ... --regression ...` to ready it.

Compound shell: `--proof "run: sh -c 'cmd1 && cmd2'"`
