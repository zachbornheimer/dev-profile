# 9. AI-facing command contract

Agents get a tiny, deterministic contract. Machine config makes the wrong action unnecessary.

```
mise run dev
mise run fmt
mise run test
mise run check
mise run e2e
```

Plus the existing devops set when the repo has it: `setup`, `lint`, `scan`, `ci`, `build`, `doctor`.

## Rules

- Do not name npm, pnpm, aube, uv, Composer, or `go test` as the user-facing command. Those may appear **inside** a mise task.
- Do not install runtimes by hand; `mise run` installs configured `[tools]`.
- Do not choose ports. Do not `kill` listeners. Never `kp`.
- Do not invent `mise run dev` when the repo has no durable dev process.
- Report the `.localhost` URL, not `localhost:<port>`.

## Dev servers (when the repo has a durable `dev` task)

- **Node / Vite / React:** `portless run -- mise run dev`. URL: `https://<branch>.<repo>.localhost`. First-run CA/proxy is a human `portless trust` / `portless proxy start` — not an agent hook.
- **Laravel + Vite:** copy `worktrunk/laravel-vite.wt.toml` to `.config/wt.toml`. Distinct `hash_port`s for artisan and vite; Caddy on :8080. URL: `http://php.<branch>.<repo>.localhost:8080`.
- zq `port claim` stays until that template is in the repo.

## attention-mail (phase 1 dogfood)

| Task | Exists | Command inside            |
| ---- | ------ | ------------------------- |
| fmt  | yes    | trunk fmt + `uv run ruff` |
| test | yes    | `uv run pytest`           |
| dev  | **no** | Do not add a server       |

Proven 2026-10-03: `mise run fmt` exit 0; `mise run test` 221 passed in 2.37s.

## Profile

`cd` into any git checkout under `~/Developer/Personal` must show `DEV_PROFILE=personal` via `mise env` with no profile flag.
