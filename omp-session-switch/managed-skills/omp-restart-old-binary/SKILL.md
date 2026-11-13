---
name: omp-restart-old-binary
description: "Use when a restarted or reopened omp session is still the old build, or when close-and-open and /restart do not pick up a newly installed omp."
---

# A restarted omp can still be the old binary

A long-lived herdr zsh keeps the mise install directory from shell start on PATH, ahead of `~/.local/bin` and the mise shims. `command omp` in that shell launches the pinned file, for example `~/.local/share/mise/installs/github-zachbornheimer-oh-my-pi/build-<old>/omp`, not `mise which omp`.

Closing the pane and opening `omp` again reuses that shell, so the new process is still the old binary. `/restart` from the old binary re-execs `process.execPath`, which is the same file. Neither is a failed install.

Check with `lsof -a -p <omp-pid> -d txt` and the parent shell's PATH (`ps eww -p <zsh-pid>`). The first `omp` on that PATH is the pin. `mise which omp` and `build-latest` name the current install.

A fresh launch that reaches the new binary needs a shell whose PATH does not pin the old install, or an exec of `build-latest/omp` itself. The idle hot reload must prefer `~/.local/share/mise/installs/github-zachbornheimer-oh-my-pi/build-latest/omp` over `$which("omp")` whenever that symlink exists.

`mise up github:zachbornheimer/oh-my-pi` reports up to date while a newer release is Latest until `*oh-my-pi-latest-*.msgpack.z` is removed from the mise GitHub cache.
