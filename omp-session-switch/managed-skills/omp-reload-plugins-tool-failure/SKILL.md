---
name: omp-reload-plugins-tool-failure
description: "Diagnose \"/reload-plugins: tools reloaded ... 1 failed — index.ts: Tool must export a default function\" and enable omp hot reload settings."
---

# omp /reload-plugins tool failure

The error names only `index.ts`, not the tool. Find the offender:

1. In `~/.omp/agent/tools`, check each `*/index.ts` for `export default` OR `as default` (bundled tools end with `export { x as default }`, so grepping only `export default` gives false positives such as kill and system_one).
2. A tiny index.ts (e.g. 38 bytes, `export const foo = true;`) is a leftover stub. Delete the dir, then rerun `/reload-plugins`.
3. Run the loop through `run_command`; very large dirs may background after 20s, so use `wait` on the job.

# Hot reload settings (omp fork, build with `assembled`)
- `tools.hotReload` (tools+skills), `tools.hotReloadExtensions` default false; set true in `~/.omp/agent/config.yml`.
- `session.hotReloadBinary` default true, only re-execs inside herdr/tmux.
- Verify with `read cfg://tools/hotReloadExtensions`.
- A reload only applies on-disk changes; a running session keeps old extension code until reload or restart.
- Config.yml live-reload is not a documented setting; unverified.
