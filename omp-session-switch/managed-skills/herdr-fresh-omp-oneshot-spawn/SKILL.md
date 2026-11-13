---
name: herdr-fresh-omp-oneshot-spawn
description: Starting a fresh interactive omp in herdr that runs one prompt (e.g. /force audit-startup) and exits by itself; session-file and token-measurement gotchas
---

# Fresh one-shot omp in herdr (verified 2026-11-10)

Recipe:
1. `R=$(herdr workspace create --cwd <dir> --label <x> --no-focus)`; ids are in `result.workspace.workspace_id` and `result.root_pane.pane_id`.
2. `herdr pane run <pane> "OMP_ONE_SHOT=1 omp --model <m> --no-title -- '<prompt>'"`.
3. Wait with an armed `timer` (a `sleep` poll loop is refused by run_command), then `herdr pane read <pane> --lines 60`.
4. `herdr workspace close <ws>` when done.

Facts:
- The flag is `OMP_ONE_SHOT=1` (underscore, exact value 1). The extension `~/.omp/agent/extensions/one-shot/` shuts the TUI down at `session_stop`, so omp prints "Closing session..." and exits. Do not read the extension and `~/.config/herdr/oneshot.sh` to rediscover this: `ONESHOT_IS_ONE_SHOT` in oneshot.sh is a different thing (popup launcher).
- `/force audit-startup` as the prompt made the fresh session run `cli.ts` via run_command (not the slash command itself) and write `~/.local/state/omp-hooks/audit-startup.json`. A 54,120-token startup was reported that way.
- A one-turn interactive session wrote NO `.jsonl` into `--session-dir`, even though `herdr pane get` reports a path there; so provider usage cannot be read from the session file. The footer `NN.N%/100K` (context fraction, about 50 tokens precision) is the only interactive number seen. Cause not investigated.
- `herdr agent start/prompt --wait` also works but returns the same unwritten session path.
