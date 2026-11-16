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

There is one way to launch and one way to wait. You never sleep, never poll on a cadence, and never run a second watcher beside the job itself.

### Launch — `bash`

omp's `bash` (extended by `extensions/bash-rules.ts`) backgrounds any command that runs past about 20 s and returns a `bg_N` job id. That job lives in omp's own async job manager: its exit is delivered to the session as a native async result, and the stop hooks defer (`awaiting_async_work`) while it runs. You arm nothing.

```text
bash { command: "mise run test" }   # >20 s: backgrounded as bg_N; the exit wakes you
```

For a visible pane, use `mux_open_tab` / `mux_run`, then wait for it with the `mux-wait` CLI run through `bash` (it becomes a job like any other):

```text
bash { command: "mux-wait <pane> --pattern 'ready on :3000' --timeout 300" }   # 0 matched, 124 timeout
bash { command: "mux-wait <pane> --ready" }                                   # an agent pane's prompt is up
```

### Wait — native `wait`, or end the turn

`wait` is omp's built-in tool. It blocks on this session's own background jobs (`bg_N`, `tc_N`) and services, or on an answer owed to a question you sent; with nothing running it returns at once. The UI renders it as the native waiting card.

- Nothing left but your own jobs? End the turn instead: each result starts your next turn, and the stop hooks do not fire while the job is pending.
- A result arrived and others are still running? Act on it before waiting again.
- NEVER wait on another agent's progress, and NEVER poll (`sleep`, `ps`, log tailing) while a job runs.

Do not use `tool_call { async: true }` for long work you need to wait on: its `tc_N` completion travels the capability channel, not omp's job manager. Run long commands through `bash`.

## Why no second watcher

A job's exit is reported once, to the session that started it. A second watcher on the same exit (a poll loop, a `--watch` beside a backgrounded command) is a duplicate report at best and a busy loop at worst.

## Handling wake-ups

- Address errors or actionable events immediately. Read `log_path` and debug the issue thoroughly before settling on a root cause, as long-running processes are generally expensive. Resubmit the job once it is fixed:
  - For PRs, this means repushing the changes and restarting CI (if needed).
  - For jobs, requeue or relaunch with `bash`.
- If there are multiple jobs running, start debugging immediately when any jobs fail. Minimize total wall-time with completing tasks.
- On a relaunch, the new call returns a fresh job id; nothing needs re-pointing.

## Cleanup

- When a job is in a terminal state and its completion has been reported, you are done.
- A standing herdr pane (no `one_off`) is the one thing that does not clean itself: close its tab when the work is over.
- Do not leave detached workers or orphaned watcher processes behind.

## Examples

- Test suite: `bash { command: "mise run test" }`; on wake read `log_path`, fix, rerun.
- Dev server: start with `mux_open_tab`, then `bash { command: "mux-wait <pane> --pattern '<ready line>'" }`.
- PR CI: `bash { command: "gh pr checks 123 --watch" }`; on wake, red means fix and push, green means merge.
- Cluster job: hold it with a blocking `srun`, not `sbatch`, so the exit is the terminal event.
