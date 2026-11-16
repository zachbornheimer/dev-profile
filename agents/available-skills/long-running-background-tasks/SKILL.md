---
name: long-running-background-tasks
description: >-
  Required reading before you start, watch, or wait on anything that keeps running after you launch it — background jobs, watchers, scheduled loops, CI, pull requests, training runs, dev servers, long builds. Read it before you launch such work and before you report on its state. Saying where a running job stands counts as working on it. Use when: about to launch, supervise, inspect, diagnose, or report on work that keeps running after it is started.
---

# Working with long-running background tasks

Only submitting or queuing jobs is not sufficient to complete the task. The definition of done is the job has completed successfully and you have verified that it has produced all the expected outputs.

This means you must see through the jobs completion by watching the job to ensure that its healthy, progressing, and working as intended.

When the user says "Please spawn a tmux session" or an agent pane is glitched, spawn or restart the tmux pane and watch it through completion. Do not leave a prompt sitting for the user to hit enter.

## Tools available

There is one way to launch and one way to wait. You never sleep, never poll on a cadence, and never run a second watcher beside the one the launcher already armed.

### Launch — `bash`

omp's `bash` (extended by `extensions/bash-rules.ts`, which superseded `run_command`) backgrounds any command that runs past about 20 s and returns a job id and `log_path`; the log is where output lives. The exit wakes you; you arm nothing for the common case. Use `bash` with an explicit `timeout` for long work, or start it detached with `nohup ... &` and wait on the pid.

```
bash { command: "mise run test" }   # >20 s: backgrounded; job id + log path returned; the exit wakes you
```

For a visible pane, use `mux_open_tab` / `mux_run` instead of herdr.

### Wait — one tool, one arm, no polling

`wait` is the single settlement surface. Blocking (`{}` is the whole call) settles on the first thing this session owns: a report-back record the channel store holds, a background job that is not running, an arm that fired, or an atask task that completed. `wait` with `job_id` settles on that one job.

When you need a durable wake instead — the event may land after this turn, or you want the completion to reach a session that might not be listening — arm exactly one wait:

```text
wait {
  action: "arm",
  until: { type: "job_exit", job_id: "<id>" },
  on_fire: { notify: true },
}
```

It returns `wait_id` at once.

- `until` also takes `disk_mounted`, `path_changed`, `timer`, `job_output` (new output in a log), and `process_exit`. A `bash` job needs none of this: its exit wakes you.
- `on_fire` is `{ notify: true }`, `{ command }`, or `{ worker: { prompt } }` (files an atask draft and runs a headless worker).
- `wait`'s arm field is `one_shot` — A `one_shot` arm fires once and requires `ttl`; if the event has not come by then, `escalate` runs instead, else the arm expires.
- `status` reads (with `wait_id`: that arm; without: the newest 100). `cancel { wait_id }` unloads one.

## Why no second watcher (the invariants)

Three invariants make the armed wake the only one you need:

1. **Each fire settles exactly one wait.** The fire path claims its record exclusively, so two simultaneous fires run `on_fire` once; a fired arm is marked `delivered` when the session's `wait` reports it and never re-fires.
2. **A job exit is consumed once by its owner.** Once a wait has reported a job's exit, that job is consumed for its owner — later waits block on the remaining work instead of re-reporting it.
3. **A session wakes once per batch of report-back records.** One wake carries the batch; when the completion says `more_pending`, call `wait` again to read the rest.

So the job's own exit wake is the only wait on a launched job. There is no second waiter and no poll loop beside the launcher's arm — a second arm on the same exit, or a poll loop beside the armed one, is a duplicate report at best and a busy loop at worst.

## Handling wake-ups

- Address errors or actionable events immediately. Read `log_path` and debug the issue thoroughly before settling on a root cause, as long-running processes are generally expensive. Resubmit the job once it is fixed:
  - For PRs, this means repushing the changes and restarting CI (if needed).
  - For jobs, requeue or relaunch with `bash`.
- If there are multiple jobs running, start debugging immediately when any jobs fail. Minimize total wall-time with completing tasks.
- On a relaunch, the new call returns a fresh `wait_id`; the old job's arm settled on the old exit. Nothing needs re-pointing.

## Cleanup

- When a job is in a terminal state and its completion has been reported, you are done; the record retires with its delivery. Cancel any arm you made directly (a `timer`, a `path_changed` watch) that no longer matters, with `wait cancel { wait_id }`.
- A standing herdr pane (no `one_off`) is the one thing that does not clean itself: close its tab when the work is over.
- Do not leave detached workers or orphaned watcher processes behind.

## Examples

- Test suite: `bash { command: "mise run test" }`; on wake read `log_path`, fix, rerun.
- Dev server: start with `mux_open_tab`, then `mux_wait` with a `pattern` for the ready line.
- PR CI: `bash { command: "gh pr checks 123 --watch" }`; on wake, red means fix and push, green means merge.
- Cluster job: hold it with a blocking `srun`, not `sbatch`, so the exit is the terminal event.
