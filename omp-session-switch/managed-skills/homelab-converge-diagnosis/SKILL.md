---
name: homelab-converge-diagnosis
description: "Diagnose and fix a red mise run apply on the homelab mini: read the evo exit-code meaning, find the failing task, check for a deliberate job pause, repair LaunchDaemon LWCR drift, and prove the fix live."
---

# Homelab converge diagnosis

Use when `mise run apply` / `mise run install` / `homelabctl check` on the mini is red, or when `org.zysys.homelab-auto-update` alerts every cycle.

## Read the exit code first

`homelabctl apply` exits:

| code | summary line | meaning |
|---|---|---|
| 0 | ok | converged |
| 1 | `[blocked · warned]` | warnings only — no task failed |
| 2 | `[failed · partial · warned]` | at least one task failed (often `already mutated: N` first) |

Exit 1 with only a declared-but-absent device (e.g. `ExternalSSD /Volumes/… absent — degrading gracefully`) is environmental, not a code defect: `mise run install`/`update` then fail, and `homelab-auto-update` pushes "Homelab auto-update FAILED" every cycle. Say so instead of hunting a bug.

## Get the real failing task

`mise run apply` output is long and `| tail -40` loses the `✗` lines. Run it redirecting to a file, then grep:

```bash
ssh mini 'zsh -lic "export DOCKER_HOST=unix://\$HOME/.colima/default/docker.sock; cd ~/homelab && mise run apply" > /tmp/apply.out 2>&1; echo exit=$?'
ssh mini "grep -E '^\[apply\] +[!✗]' /tmp/apply.out | head -20"
```

`homelabctl check` is the cheap discriminator: it lists per-section findings and never mutates. Run it the same way into `/tmp/check.out`; `grep -c '✗'` counts hard failures, `⊘ … N drifted` counts repairable drift.

## Rule: an evo effect owns its resource

`evo.Effect(ctx, spec{Resource: evo.FSResource(path)}, body)` already holds the write claim on `path`. Calling `evo.File(...)` for that same path inside the body fails with:

```
evo: File "…": evo: nested resource acquisition: holding write fs:…, requested write fs:…
```

Write through the filesystem facade inside the effect instead (`files.WriteFile(path, data)`, `files.RemoveFile(path)`), as `declareHAPackageRemoval` does. An effect that does *not* declare `Resource:` may use `evo.File` directly (`declareHAPackageSync`).

## Rule: a running job defers its reload, and a replaced binary invalidates the LWCR

`launchctl print system/<label>` showing `properties = … | needs LWCR update …` means every spawn fails **exit 78** while the plist is byte-identical — a deploy that replaces the binary (`~/.local/state/deploys/<sha>/bin`) does this. File comparison cannot see it; `install_plist` must ask launchd (`daemon_needs_lwcr_update` there) and re-bootstrap. A job that is currently *running* is deferred by design: its reload lands on the next restart, so leave it.

## Check for a deliberate pause before believing "not loaded"

```bash
ssh mini 'cd ~/homelab && bash scripts/mini-jobs.sh status'
ssh mini "sudo -n launchctl print-disabled system | grep -E 'zysys'"
```

`mini-jobs.sh pause` (no labels) disables the watchdog, the auto-update deploy and every media mover; a disabled job survives a reboot *and* apply's re-bootstrap. `resume` (no labels) re-enables exactly that default set — it does **not** touch jobs disabled individually (`relay-agent`), so those are deliberate: leave them and report.

## Bash pitfall that costs hours

`set -euo pipefail` plus `cmd | grep -q pattern` is a race: grep exits early, the writer takes SIGPIPE, `pipefail` reports 141, and a *match* reads as failure. Flaky in tests, silent in production. Capture the output and match in bash:

```bash
out="$(cmd 2>/dev/null || true)"
[[ ${out} == *pattern* ]]
```

## Prove it

A fix is not done until the mini shows it:

```bash
ssh mini 'zsh -lic "export DOCKER_HOST=unix://\$HOME/.colima/default/docker.sock; cd ~/homelab && mise run install" > /tmp/install.out 2>&1'
ssh mini "grep -E 're-bootstrapping|reloaded:' /tmp/install.out"
```

then re-run `homelabctl check` and compare the drifted count and `✗` count against the numbers you took before. Land code changes through a PR (`wt pr`, `gh pr merge`) — a direct push to `main` is refused by a hook. A **mode-only** change is dropped by GitHub's squash merge; land it with `gh pr merge --merge` and confirm with `git ls-tree origin/main <path>` showing `100755`.
