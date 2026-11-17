# History watcher executable selection

The `history-watch` builtin freezes the executable running bootstrap. On this Mac the generated service selected `~/.local/bin/mise`, which resolves to Homebrew 2026.11.8 rather than the configured fork 2026.11.9. Sampling the old watcher showed capture repeatedly opening Git pack indices while holding the operation lock. The installed fork already opens that repository once per capture (`crates/mise-system/src/history/shadow.rs:487`).

The mise shim alone is insufficient: under launchd's minimal environment, `mise --version` through the shim returned Homebrew 2026.11.8. Explicit `mise exec github:zachbornheimer/mise -- mise --version` returned 2026.11.9. The service now uses that explicit tool selection for `dot watch`, preserving user scope and on-failure restarts, and requiring installed tools.

Service command strings do not render `{{env.HOME}}`: launchd receives that literal and exits 78. Use the documented `~/` program prefix, expanded by mise's LaunchAgent renderer. The regression rejects unrendered template delimiters.

`tests/bin-path-free.sh` protects the declaration. It failed before each fix with an assertion identifying the obsolete binary selection, then passed after the declaration changed. The live config is tracked independently of this repository and must receive the matching service block before `mise bootstrap services apply` deploys it. No build directory is pinned, lock is removed, or concurrent publisher is terminated.
