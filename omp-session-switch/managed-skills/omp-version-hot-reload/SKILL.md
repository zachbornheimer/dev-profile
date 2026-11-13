---
name: omp-version-hot-reload
description: "Use when an omp session should pick up a newly installed omp build, or when close-and-open still runs the old binary. Covers the idle herdr/tmux re-exec and the mise PATH pin that makes $which(\"omp\") lie."
---

# omp version hot reload

Idle omp inside herdr or tmux re-execs when mise `build-latest` moves. A change during a turn waits until the turn ends. Setting: `session.hotReloadBinary` (default on). A plain terminal never auto-restarts.

## Did it reload? Check the binary, not the PID

A hot reload is an in-place `exec`: the PID and `ps` ELAPSED stay the same, and the command line gains `--restore <session file>`. Do not read "same PID, old uptime" as "not reloaded". `ps` also truncates the path; `cut` can hide the build tag. The only proof is:

```bash
lsof -a -p <pid> -d txt | grep omp   # txt path names build-<tag>/omp
```

Symptoms of a reload in progress: every tool call fails with `onPreToolUse.ts timed out after 30000ms` and the tool list changes. That is the extension host restarting, not a fault. `omp --version` from another process only reports what a fresh launch would run.

## The PATH pin

A long-lived mise shell puts the install directory from shell start on PATH ahead of `~/.local/bin` and the mise shim. `command -v omp` and `$which("omp")` then return that pinned binary, not the current build. Closing and reopening a pane from that shell relaunches the pin. `/restart` on a binary that predates `restartLiveExecutable` re-execs `process.execPath` and cannot jump either.

The watcher and `/restart` must prefer `~/.local/share/mise/installs/github-zachbornheimer-oh-my-pi/build-latest/omp` (realpath) over any PATH hit whenever that symlink exists. `$which("omp")` is only the fallback when the symlink is missing.

A fresh launch that follows the shim:

```bash
env -i HOME="$HOME" PATH="$HOME/.local/bin:/usr/bin:/bin" "$HOME/.local/bin/omp" --version
```

## Land and install

Custom omp is fork `main` plus the single `assembled` branch (`.omp-build/branches/assembled.toml`). Cherry-pick onto `assembled`. Do not merge a topic branch cut from an older main: that pulls unrelated history. Push `origin assembled`, then:

```bash
gh workflow run omp-build.yml --repo zachbornheimer/oh-my-pi --ref main
```

mise caches the latest GitHub release. Drop `*oh-my-pi-latest-*.msgpack.z` under `~/.cache/mise/github` and `~/Library/Caches/mise/github` before `mise up github:zachbornheimer/oh-my-pi`. The installed binary is current only when `rg -a -c -F session.hotReloadBinary "$(mise which omp)"` is greater than 0 and `omp --version` names that release. That `rg` scans a ~230 MB binary and can exceed the 20s foreground limit; run it as a background job.
