---
name: omp-path-pin
description: "Use when a restarted or newly opened omp is still an older build than mise which omp, or when an idle hot reload does not pick up a new omp install."
---

# omp PATH pin

A long-lived zsh, including a herdr pane, keeps the mise install directory that was active when the shell started ahead of `~/.local/bin` and the mise shim. `command omp` in that shell relaunches that pin, not `mise which omp` and not `build-latest`.

1. Confirm with `lsof -a -p <omp-pid> -d txt`. The `txt` path is the binary actually running.
2. Compare it to `readlink ~/.local/share/mise/installs/github-zachbornheimer-oh-my-pi/build-latest`.
3. To start the current build from a pinned shell, exec the absolute `build-latest/omp` (or `build-<tag>/omp`). Do not rely on `command omp` or close-and-open in that shell.
4. Idle hot reload (`session.hotReloadBinary`, herdr or tmux, compiled binary only) must prefer `build-latest/omp` over `$which("omp")`. A session still on an older binary cannot re-exec onto a newer one.
