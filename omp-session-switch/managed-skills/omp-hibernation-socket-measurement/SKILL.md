---
name: omp-hibernation-socket-measurement
description: "Use when measuring whether the omp session-hibernation extension releases Postgres sockets/RSS, or debugging idle omp resource use on this Mac."
---

## Gotchas (verified 2026-11-10, build-20261110031722)

- **Postgres sockets are a startup burst, not a leak.** A fresh omp opens ~20 TCP sockets to :5432 (12 to the sessions DB, 4 + 4 to two other hosts) and ALL close by ~22s via pool `idleTimeout` (session storage `SQL_POOL_OPTIONS = {max:2, idleTimeout:5}` in `packages/coding-agent/src/session/session-storage-env.ts`; zab memory pool `{max:2, idleTimeout:10}` in `~/.omp/agent/extensions/zab-ai-tools/catalog_ports.ts`). Steady-state idle: 0-2 sockets. Hibernation does not need to be credited or blamed for this.
- **Never judge socket release within ~30s of process start or right after `/reload-plugins`**: reload reopens connections (saw 15-16) and looks like a failed close. Sample after 30s idle.
- **Measure**: `lsof -a -p <pid> -iTCP -n -P`, count ESTABLISHED per remote `ip:5432`. Run the sampler as a python script (time.sleep inside python is fine); a bare `sleep` in run_command is refused. Long scripts get promoted to a background job: use `wait` with job_id, then read its log_path.
- **RSS barely drops on hibernate** (~0.9 MB reclaimed on macOS; `Bun.shrink()` returns little). Don't expect memory wins from hibernation alone.
- `catalog_ports.ts` (the `closeMemoryConnections` export) has been overwritten by the dotfiles sync (`mise dot`) once; after a sync, grep that the export still exists at ~line 188 before testing `close_pools`.
- Hibernation log: `~/.omp/agent/logs/session-hibernation.jsonl` (events: loaded, scheduled, hibernate, dehydrate_step close_pools/drain_storage, wake).
- `mise install` then `mise use latest` can lag new releases; verify the actual build dir name in `~/.local/share/mise/installs/github-zachbornheimer-oh-my-pi/` before testing on "the new build".
