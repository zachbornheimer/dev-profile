---
name: setup-discovery
description: TRIGGER when the user says "install X", "set up Y", "add Z", "configure ...", or names a tool/runtime/dependency to bring onto the machine. Verify what the target actually is and what it needs BEFORE proposing any install command or edit. Do not run installs until discovery is done.
---

# Setup Discovery

Rigid interior, idiot-proof exterior: never install or configure something you
have not first identified, inspected, and de-risked. A wrong install wastes time
and can leave the machine in a half-configured state.

## Protocol

1. **Identify the target.** Determine what X/Y actually is. If the token is
   ambiguous (a project name, an alias, an acronym, a guessed package), ask ONE
   clarifying question and stop until answered. Never infer a package from a name
   you do not recognize — but run `command -v` and `--version` first; an existing
   install turns "install" into upgrade, pin, or configure.
2. **Verify it exists and map its feature set.**
   - `command -v <bin>` / `which <bin>` to check if it is already present.
   - `<tool> --version`, `<tool> --help`, `man <tool>` for real flags and subcommands
     (do not trust memory of the CLI surface).
   - Read the upstream README / spec for install paths and required features.
   - Record what the tool can and cannot do — this drives installer choice.
3. **Confirm prerequisites.**
   - Runtimes the installer needs: `command -v npx node pnpm bun uv pipx brew mise`.
   - Target directories exist and are writable; correct permissions.
   - Network/registry reachability if it fetches at install time.
   - Existing conflicting install (PATH shadowing, stale version).
4. **Only then propose the installation approach.** State the chosen method, why
   it beats the alternatives, and exactly what it will change. Then execute.

If any step blocks (missing prereq, ambiguous target, no writable location),
surface the blocker and the fix — do not fall back to a guess.

## Decision tree — pick the installer

Ask in order; take the first that fits:

1. **System package manager** (`brew`, `apt`, `dnf`, `pacman`): use when the tool
   is a system-level binary or service, is already packaged, and the package
   manager can manage upgrades. Prefer this for machine-wide CLIs and daemons.
2. **Language-specific installer** (`npm/npx`, `pnpm`, `bun`, `uv/pipx`, `cargo`,
   `go install`): use when the tool is a language ecosystem package, needs an
   isolated environment, or the user wants per-project pinning. Prefer `pipx`/`uv`
   over bare `pip` for global Python CLIs.
3. **Wrapper script**: use when the tool has no package, is a single-file script,
   needs custom bootstrap logic, or must pin a specific version/URL. Put it in a
   managed bin dir (`~/.local/bin`) and keep it idempotent.
4. **Config file** (dotfiles, `mise.toml`, `.tool-versions`, JSON/YAML config,
   `chezmoi` template): use when "setup" means enabling/configuring an already
   installed capability rather than installing new binaries. Edit the live file,
   then re-add to chezmoi if it is managed.

Never bypass the repo's task runner (`mise`) for project-level setup, and never
hand-edit generated config — change the source template.

## Hard rules

- Discovery before installation, always. No command proposed until steps 1-3 pass.
- Names describe WHAT, not HOW; verify the real binary and flag names from `--help`.
- Leave the machine idempotent: re-running the setup must not duplicate or break state.
- After installing, prove it: run the tool's version/health command and report the real output.

## Verified example — aube

- Identity: `aube`, the project documented at `aube.jdx.dev` (301s to the canonical `aube.sh`; @jdxcode).
- Already installed: `which aube` → mise install `2.7.0` (macos-arm64). `aube --help`
  reports "A fast Node.js package manager" plus a `config` subcommand that reads and
  writes `.npmrc`; the same run reports `2.8.0` available.
- So "set up aube" is the **config file** branch, not an installer. Setup means
  `.npmrc` settings; the only open choice is whether to upgrade to 2.8.0.

The trap: answering a setup request with an installer because the tool name is unfamiliar.
