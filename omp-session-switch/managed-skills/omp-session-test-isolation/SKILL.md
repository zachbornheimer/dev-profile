---
name: omp-session-test-isolation
description: Use when running or editing oh-my-pi session storage and listing tests (packages/coding-agent/test/session/) so ~/.omp/.env and mise shims do not inject live Neon SESSIONS_DB_URL into bun test.
---

# Isolating `oh-my-pi` Session Tests from Live `SESSIONS_DB_URL`

## Why Simple `env -u SESSIONS_DB_URL bun test` Fails on This Machine

Three layers re-inject `SESSIONS_DB_URL` (pointing at the live Neon PostgreSQL `omp_session_files` table) into `bun test`:
1. **The `mise` shim (`~/.local/share/mise/shims/bun`)** re-evaluates `~/.config/mise/config.toml` `[env]` before exec'ing `bun`, overwriting `env -u SESSIONS_DB_URL`.
2. **Bun's `.env` autoloader** reads `.env` from the current working directory unless `--env-file=/dev/null` is passed.
3. **`@oh-my-pi/pi-utils/env` (`packages/utils/src/env.ts`)** reads `~/.omp/.env` and `~/.omp/agent/.env` on module import and populates any key where `!Bun.env[key]` is falsy (so both `undefined` and `""` get overwritten by `~/.omp/.env`).

If `SESSIONS_DB_URL` remains set during `packages/coding-agent/test/session/*.test.ts`, tests that omit an explicit `SessionStorage` connect to live Neon Postgres, fail on local-only assertions, and write `/var/folders/...` test rows into `omp_session_files`.

## Exact Command to Run `oh-my-pi` Session Tests Isolated

Always bypass the `mise` shim, disable Bun `.env` autoloading, and redirect `PI_CODING_AGENT_DIR` / `PI_CONFIG_DIR` away from `~/.omp`:

```bash
/usr/bin/env -u SESSIONS_DB_URL -u OMP_SESSION_DB_URL -u OMP_SESSION_PATH_PREFIX_ALIAS \
  PI_CODING_AGENT_DIR=/tmp PI_CONFIG_DIR=.nonexistent \
  /Users/zbornheimer/.local/share/mise/installs/bun/latest/bin/bun --env-file=/dev/null test \
  packages/coding-agent/test/session/
```

## Pre-Push Scanner (`foxguard-typescript`) Rules for `packages/coding-agent/src/session/`

- **SQL table identifiers (`js/no-sql-injection`)**: Do not use template literals like `` `SELECT ... FROM ${table}` ``. Use a helper `bindTable("SELECT ... FROM {table}", table)` (`statement.replaceAll("{table}", table)`) after validating `IDENT_RE.test(table)`.
- **`Map.get` named `headers.get(...)` (`express-ssrf`)**: Semgrep flags `headers.get(entry.file)` as an Express request header read. Iterate `[...headers]` or rename the `Map` variable (e.g., `headerByFile.get(entry.file)`).
