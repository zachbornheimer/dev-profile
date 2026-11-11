---
name: long-running-background-tasks
description: >-
  Required reading before you start, watch, or wait on anything that keeps running after you launch it — background jobs, watchers, scheduled loops, CI, pull requests, training runs, dev servers, long builds. Read it before you launch such work and before you report on its state. Saying where a running job stands counts as working on it. Use when: about to launch, supervise, inspect, diagnose, or report on work that keeps running after it is started.
---

# Working with long-running background tasks

Only submitting or queuing jobs is not sufficient to complete the task. The definition of done is the job has completed successfully and you have verified that it has produced all the expected outputs.

This means you must see through the jobs completion by watching the job to ensure that its healthy, progressing, and working as intended.

When the user says "Please spawn a tmux session" or a Grok pane is glitched, spawn or restart a Grok tmux pane and watch it through completion. Do not leave a prompt sitting for the user to hit enter.

## Tools available

There is one way to launch and one way to wait. You never sleep, never poll on a cadence, and never run a second watcher beside the one the launcher already armed.

### Launch — run_command with background: true

Everything that keeps running after you launch it goes through `run_command` with `background: true`. It runs detached and returns at once with `job_id`, `pid`, and `log_path` — the log is where output lives; nothing else streams it to you.

- `where: "herdr"` places it in a herdr tab or pane (a terminal multiplexer session that survives your shell); it returns `tab_id` and `pane_id` instead of a pid, with output tee'd to `log_path`. Without a preference, omit `where` and the launcher picks a process job.
- `one_off: true` (herdr) marks the command as a single task that will exit: the pane command wraps an exit sentinel, and completion reaches you without any arm you write. A standing pane (no `one_off`) has no exit event — it stays until you close it.
- `on_complete` says what runs at the exit: `"wait"` (arm nothing — you will settle it with `wait` yourself), `"notify"`, or `{ command: string }`. on_complete defaults to "notify", so the common case is: launch, get `wait_id` back, and the exit reports itself.
- The return carries `wait_id` when an arm was made — the handle the completion fires on. Keep it for `wait`'s `status` and `cancel`.

```python
run_command(
    command="npm test",
    purpose="run the suite detached",
    background={"where": "herdr", "one_off": True},
)
# status ok; where herdr; tab_id/pane_id; log_path; wait_id w-…; the exit reports itself
```

### Wait — one tool, one arm, no polling

`wait` is the single settlement surface. Blocking (`{}` is the whole call) settles on the first thing this session owns: a report-back record the channel store holds, a background job that is not running, an arm that fired, or an atask task that completed. `wait` with `job_id` settles on that one job.

When you need a durable wake instead — the event may land after this turn, or you want the completion to reach a session that might not be listening — arm exactly one wait:

```
wait {
  action: "arm",
  until: { type: "job_exit", job_id: "<id>" },
  on_fire: { notify: true },
}
```

It returns `wait_id` at once.

- `until` also takes `disk_mounted`, `path_changed`, `timer`, `job_output` (new output in a log), and `process_exit`. A herdr `one_off` needs none of this from you: it arms `log_sentinel` for you on the pane's log — the sentinel it appends is the exit event, and its fire writes the completion record.
- `on_fire` is `{ notify: true }`, `{ command }`, or `{ worker: { prompt } }` (files an atask draft and runs a headless worker).
- `wait`'s arm field is `one_shot` — distinct from `run_command`'s `one_off`, which names a single-task herdr pane. A `one_shot` arm fires once and requires `ttl`; if the event has not come by then, `escalate` runs instead, else the arm expires.
- `status` reads (with `wait_id`: that arm; without: the newest 100). `cancel { wait_id }` unloads one.

## Why no second watcher (the invariants)

Three invariants make the armed wake the only one you need:

1. **Each fire settles exactly one wait.** The fire path claims its record exclusively, so two simultaneous fires run `on_fire` once; a fired arm is marked `delivered` when the session's `wait` reports it and never re-fires.
2. **A job exit is consumed once by its owner.** Once a wait has reported a job's exit, that job is consumed for its owner — later waits block on the remaining work instead of re-reporting it.
3. **A session wakes once per batch of report-back records.** One wake carries the batch; when the completion says `more_pending`, call `wait` again to read the rest.

So `on_complete: "notify"` is the only armed wait on a launched job. There is no second waiter and no poll loop beside the launcher's arm — a second arm on the same exit, or a poll loop beside the armed one, is a duplicate report at best and a busy loop at worst.

## Handling wake-ups

- Address errors or actionable events immediately. Read `log_path` and debug the issue thoroughly before settling on a root cause, as long-running processes are generally expensive. Resubmit the job once it is fixed:
  - For PRs, this means repushing the changes and restarting CI (if needed).
  - For jobs, requeue or relaunch with `run_command background: true`.
- If there are multiple jobs running, start debugging immediately when any jobs fail. Minimize total wall-time with completing tasks.
- On a relaunch, the new call returns a fresh `wait_id`; the old job's arm settled on the old exit. Nothing needs re-pointing.

## Cleanup

- When a job is in a terminal state and its completion has been reported, you are done; the record retires with its delivery. Cancel any arm you made directly (a `timer`, a `path_changed` watch) that no longer matters, with `wait cancel { wait_id }`.
- A standing herdr pane (no `one_off`) is the one thing that does not clean itself: close its tab when the work is over.
- Do not leave detached workers or orphaned watcher processes behind.

## Examples

### Example: a detached test suite

```python
run_command(
    command="npm test",
    purpose="run the suite detached",
    background={"where": "herdr", "one_off": True},
)
```

The exit reports itself with the tail of `log_path` in the completion body. Read `log_path` for the full failure output when it lands, fix, and relaunch the same way.

### Example: a dev server

A dev server never exits, so `one_off` is wrong: place it as a standing pane and arm on its output.

```python
run_command(
    command="npm start",
    purpose="dev server on :3000",
    background={"where": "herdr", "on_complete": "wait"},
)
# standing pane; no exit arm — arm on the log_path it returned
```

```
wait {
  action: "arm",
  until: { type: "job_output", log_path: "<log_path>" },
  on_fire: { notify: true },
}
```

Each new output in the log wakes you once; read the tail of `log_path` for the compile error or port conflict, fix it, and hot reload picks the fix up without restarting the pane. If the process is dead, restart it with a fresh `run_command` and re-arm on the new `log_path`.

### Example: CI on a pull request

```python
run_command(
    command="gh pr checks 123 --watch",
    purpose="watch PR 123 CI",
    background={"where": "herdr", "one_off": True},
)
```

The one-off exits when CI settles and the sentinel's fire writes the completion record; a blocking `wait` reports it, and the default notify arm wakes you instead of holding. When the completion lands:

- CI red: read the failure from the completion body, fix in the code, push; relaunch the watch on the new head.
- Mergeable: tell the user, merge, and cancel any standing arm you still hold.

### Example: a long training job

Terminal conditions are the job failing or completing — both are an exit. Hold the job inside the pane so its exit is the terminal event: `srun` blocks until the cluster job ends, while `sbatch` returns at once and would end the one-off immediately.

```python
run_command(
    command="srun --gpus=8 python train.py",
    purpose="launch the training run",
    background={"where": "herdr", "one_off": True},
)
```

When the wake lands, report the state (`sacct`, the tail of the run log — `job_exit` carries the exit code), and if it failed, debug thoroughly, fix, and relaunch with a fresh arm on the new run.
