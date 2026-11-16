# Known issues (dated snapshot, 2026-10-22)

These rot. Re-verify before acting; each line says how. Repo HEAD was `9d1855e`; the installed
`~/.cargo/bin/agent-hooks` was built Oct 18 from `fdab1b9`.

## Live config (`~/.config/agent-hooks/hooks.toml`)

- **23 of 69 rows have no `command`** (19 `policy=`, 4 `script=`) and never run. Re-audit with
  `scripts/audit-catalog.py`. Evidence: the scripts' last `hooks.log` lines are 2026-10-15/16 (11 named guards).
  Row name -> script that exists in `~/.agents/hooks/` (executable):
  pretooluse-two-strikes-gate, -gate-bypass-tripwire (x2 rows, one script), -layout-guard (x2 rows, one script),
  -process-kill-guard, -worktree-lifecycle-guard, -subagent-model-guard, -ghx-reminder,
  posttooluse-bash-signature-record (`bash-signature-record.py`), posttooluse-edit-record (`edit-record.py`),
  posttooluse-agent-spawn-record (`agent-spawn-record.py`). `pretooluse-tool-steer` is superseded by the live
  `bash-tool-steer`. **No script exists** for output-budget, output-limit, wait-loop, repeat-command, python-editor.
  The four `script=` rows (missing-tool-discovery, escalation-budget, grep-binary-detect,
  grep-self-referential-suppress) point at `handle(event)`-only modules, mode 644, with no `__main__`: a `command`
  would not run them until they get a `run_hook` wrapper and `chmod +x`.
- **Confirm intent before re-enabling a stub.** `hooks.toml` has been in git only since 2026-10-21 and the stubs
  predate it; several would be `on_failure="block"` guards, so enabling one changes live behavior. Dry-run each deny
  path first.
- `stop-payload-dump-tmp` uses `command = ["sh", ...]` under `shell = true` and is broken (see SKILL.md Command forms).

## Tooling

- **`~/.agents/hooks/chezmoi-guard.py --check` always fails** with "could not read drift report": `chezmoi_drift.py`
  runs `~/.agents/hooks/bin/chezmoi-drift.sh`, which does not exist (the script is `~/.agents/bin/chezmoi-drift.sh`,
  and that one fails on a missing `../hooks/hook-common.sh`). Use `chezmoi status` and `chezmoi re-add -n -v` instead.
- `suggested-timeout-for.py` needs `hyperfine` and reports `ceil(p95)` with no headroom.

## agent-hooks code

- **Context cap panic**: `capped_context` in `src/adapters/claude.rs` slices the context at byte 10 000. A multibyte
  character on that boundary panics (exit 101). Reproduced with 9999 ASCII bytes plus `é`, on both the installed
  binary and HEAD. Applies to omp's shared adapter encode; Codex is uncapped.
  The cap applies to the joined context of all hooks.
- **Codex**: the encoder emits top-level `decision:"deny"|"ask"|"allow"` and, for Stop retry/halt, `deny` while
  dropping `stopReason`. Codex's published schemas accept `decision` as `approve`/`block` and Stop only as `block`
  [INFERENCE from upstream schema and `codex.rs`; not exercised against a live Codex], so Codex denies and Stop
  blocks may be rejected as invalid output.
- **Signal-killed hooks**: a hook killed by a signal has no exit code, and the adapters treat that as 0, a silent pass
  even under `on_failure="block"`.
- **Duplicate-name check is dead code**: `validate` can never see duplicates because assembly replaces them first.

## TypeSafe hook plumbing (see `typesafe-batching.md`)

- `~/.agents/hooks/state/completion-gate-judgments.jsonl` was about 232 MB / 17 783 rows with no rotation. Only
  9 672 rows (older ones) carry `request` and `response`; no row has a `model` or hop field.
- Fail-open (no verdict) rates were 40 percent on Oct 2, 58 percent on Oct 8, and 62 percent on Oct 15, peaked near 73 percent on
  Oct 17, then fell to 2, 5, and 0 percent on Oct 20, 21, and 22. Causes overall: `http 402` 1 979 (Oct 2 and 8 were almost all 402), `http 400`
  1 082 (all 510 on Oct 15), `cli-missing` 1 250. `systemone._post` discards the 4xx body, so causes beyond the
  status code are not diagnosable.
