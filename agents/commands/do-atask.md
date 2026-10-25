---
description: Delegate the task atask claim assigns, in its own herdr pane
argument-hint: "[--project <name>]"
---

Delegate one atask objective. Do not list tasks and do not choose one. `atask claim` assigns the oldest eligible task.

1. Call `start_atask_task` with no `id`. When the caller passed `--project <name>`, pass that as `project`; otherwise omit it. Use `{ onComplete: "nil", timeout_s: 120 }`. The capability runs `atask claim`, which assigns the task, then starts the worker. The worker runs in its own herdr pane, split off this one, and that pane closes itself when the worker exits. `nil` leaves the branch in place so the result can be reviewed before it lands.
2. Report the task id atask assigned, the branch, the worktree, and the worker's transcript id (`omp:<session id>`, from `~/.omp/agent/sessions` under the worktree's session directory).
3. When the call answers `running`, call `start_atask_task` again with that same id to attach. It watches the same pane and never starts a second worker. Repeat until the task settles, then report the verdict.
4. When the call answers `failed` or `refused`, report the error and stop. Do not retry a refusal, and do not claim a different task to replace it.
