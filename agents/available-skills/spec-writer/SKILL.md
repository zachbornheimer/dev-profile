---
name: spec-writer
description: Use when the user has an idea to turn into a spec or wants to be interviewed about it ('write a spec', 'spec this out', 'interview me', 'I have an idea', 'socratic', 'rfc', 'design doc for X'), from any directory including ~. Runs the capability gateway's Jev-graded Socratic interview, writes spec.md + seed.json, then hands the acceptance criteria to atask.
user-invokable: true
disable-model-invocation: false
argument-hint: '[the idea, or an interview session_id to resume]'
---

# Spec writer

The interview and the spec live in two gateway capabilities, so this works from any harness and any directory:

- `interview`: one Socratic question per call. Ouroboros's ambiguity gate decides when to stop. TypeSafe Jev grades four dimensions: goal, constraints, success criteria, and, for an existing repo, context.
- `crystallize_spec`: turns a finished interview into `spec.md` (Spec Kit headings, RFC 2119 requirements, acceptance criteria with verify commands) and an immutable `seed.json`.

Sessions and specs are stored centrally in `~/.local/share/specs/<session_id>/`, wherever you start.

## Spec Kit repo

If the directory has `.specify/`, the same loop is also a Spec Kit command. Install once from capability-replicas:

```bash
specify extension add --dev --force mastra/spec-kit/extension
specify preset add --dev mastra/spec-kit/preset
```

Then the user can say `/speckit.socratic.interview`. That command calls these same gateway tools. `/speckit.plan` and `/speckit.tasks` follow. After tasks, the hook asks whether to file each task as an atask objective. Do not file tasks yourself when that command is the one running.

## Loop

1. **Start.** Call `interview` with `{ idea: <the user's words, verbatim>, cwd: <current working directory> }`. If the user names a repo or atask project, pass `project`. When `cwd` is `~` or outside git, the work is greenfield. Inside a repo, it is brownfield and the repo becomes context.
2. **Ask.** Show `question` through the harness's own ask tool when it has one (omp `ask`, Claude Code `AskUserQuestion`), as free text. Otherwise ask it in plain chat. Each turn, add one short line: `round N · ambiguity 0.xx (<milestone>)`. Scoring starts after round 3. Don't answer for the user, and don't stack questions.
3. **Continue.** Call `interview` with `{ session_id, answer: <the user's reply, verbatim> }`. Repeat steps 2 and 3 until `status` is `ready`.
   - If the user says "just write it" or "skip", go to step 4 with `force: true`. The spec then records `gate_forced`.
   - To resume later, call `interview` with the stored `session_id` and the answer to its pending question.
4. **Crystallize.** Call `crystallize_spec` with `{ session_id }`. Add `repo: <absolute checkout path>` when the work belongs in a repository, so a copy also lands at `<repo>/specs/<session_id>/`. If the work started in `~` and the target repo is unclear, settle it first with `select_project`, or ask once.
5. **Report.** Give the spec path, the final ambiguity, and the acceptance criteria count. Show the spec's goal and acceptance criteria. Don't paste the whole file.
6. **Execute (only when the user wants it built).** Pass the spec's acceptance criteria to `plan_tasks` so they become atask objectives with real proofs. Run them with `start_atask_task` and pass `timeout_s` under the host's MCP timeout. In a repo that already uses Spec Kit, `/speckit.plan` can consume `spec.md` directly.

## Deepening

When the feature needs invariants, a failure taxonomy, concurrency, or crash-recovery contracts, run `references/rfc-deepening.md` over the crystallized spec. It extends the spec and never restarts the interview.

## Rules

- The capabilities own the questions, the scoring and the gate. Don't run a manual interview alongside them, and don't override `status`.
- Never invent answers or requirements the user did not give. Deferred items are fine: the grader does not penalize "decide later".
- If a capability call fails, report its error verbatim and file the defect with atask. Don't hand-roll the interview as a fallback.
