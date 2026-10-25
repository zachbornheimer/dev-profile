# Cross-language footguns

The highest-signal content — the mistakes Claude makes by default on this stack.
This is a seed; **grow it from real failures**: when a worker trips, add the
specific gotcha here rather than re-explaining it next time.

## Go

- A non-nil interface holding a nil pointer is `!= nil`. Check the concrete value.
- `context.Context` is always the first parameter, never stored in a struct.
- Copying a struct that contains a `sync.Mutex` by value breaks it — pointer receiver.
- Loop-variable capture in goroutines pre-1.22; wrap or shadow.
- `errgroup` for parallel work with shared cancellation; `%w` to wrap; `slog` for logs.

## TypeScript / React

- `useEffect` for derived state is always wrong — `useMemo` or compute inline.
- Default exports break tree-shaking and naming consistency — named exports only.
- `any` silently disables the type system — use `unknown` and narrow.
- CSS: Grid for 2D layout, Flexbox for 1D alignment; tokens as custom properties.

## Python

- Bare `except` catches `SystemExit` / `KeyboardInterrupt` — catch specific types.
- `threading` for I/O blocks the loop — `asyncio` + `httpx`.
- `Optional[X]` / `Union` are legacy — `X | None`. `dict` where a `dataclass` belongs.
- `os.path` is legacy — `pathlib`.

## SQL / Postgres

- `FLOAT` / `DOUBLE` for money → IEEE rounding errors. Use `NUMERIC`.
- `TIMESTAMP` without zone is ambiguous — `TIMESTAMPTZ`. `JSON` can't index — `JSONB`.
- `CREATE INDEX` locks the table — `CONCURRENTLY` on live tables.
- `SELECT *` in app code breaks on schema change; parameterize always.

## PHP

- `@` error-suppression hides the real error; instantiating deps inside a class
  makes it untestable (inject); `FLOAT` for money.
- WordPress: `$wpdb->prepare` always, `esc_*` output, `sanitize_*` input, nonces.

## Perl

- Subroutine prototypes change call-site parsing — they are NOT type hints.
- `croak` not `die` for caller errors; always check `open`; `use strict; use warnings`.

## Shell

- Missing `set -euo pipefail` → silent failures + undefined-var substitution.
- Unquoted variables break on spaces/globs; `[[ ]]` not `[ ]`; never parse `ls`.
