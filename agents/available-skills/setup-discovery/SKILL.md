---
name: setup-discovery
description: Identify software and verify its capabilities and prerequisites before proposing an installation or setup method. When the user asks to install a tool or set something up, discover what they mean and verify the environment before recommending an approach. Do not jump from a product name or assumed use case to an installer.
---

# setup-discovery

Load before the first command of any "install X", "set up Y", or "make Z global"
request. A product name is not an installer, and a tool's own "done" message is
not evidence that it wrote where you wanted.

## Protocol

1. **Identify the target.** Say in one sentence what X actually is: a CLI, a
   package, a set of files, a plugin, a config change. If the name could mean
   more than one thing, or the scope ("globally", "for my machine") is not
   pinned to a real path, ask one narrowing question. Never let scope default.
2. **Verify the target exists and read its feature set.** `command -v X`,
   `X --help`, `man X`, the project README. Record which subcommands matter,
   which flags select scope, and whether an output-directory flag exists. Do
   not assume a flag exists because a similar tool has one.
3. **Confirm prerequisites.** Interpreter or package runner present (`npx`,
   `uv`, `bun`, `mise`), destination directories exist and are writable,
   permissions, network reach, disk, package-store health. State each check and
   its result. A stale package store surfaces here, not as a mystery mid-install.
4. **Only then propose the approach.** Name the mechanism, the exact paths it
   will write, and the command that will prove it afterward. Approval is for the
   write set, not just the tool name.

## Decision tree

- **System package manager** (`brew`, `apt`) — a user-facing binary the OS
  should own. Wrong for anything that manages its own files inside `$HOME`.
- **Language-specific installer** (`npm -g`, `uv tool install`,
  `cargo install`, `mise`, the project's own CLI) — the project documents that
  channel, and you want its native version/update behavior. Watch for
  installers that choose global vs project scope by themselves.
- **Wrapper script** — the tool has no flag to confine its writes, but those
  writes derive from `$HOME` or an env var. Run it under a throwaway HOME and
  copy the result where it belongs. Also right when you must enforce a single
  write root the tool does not support.
- **Config file** — the goal is a setting, not an installation. If "make it
  global" or "point it at this directory" is expressible as an option value,
  edit the config and skip the installer.

## Never

- Propose a command before step 2 made the actual write set visible.
- Treat the tool's success output as proof of confinement. Snapshot the write
  roots before and after and diff them.
- Assume a symlink means escape, or a missing escape. Resolve the path and
  compare inodes: a write reached through `~/.grok/skills` may land inside
  `~/.agents/available-skills` and be perfectly correct.
- Hand-edit a lock file or generated tree to make a check pass.
