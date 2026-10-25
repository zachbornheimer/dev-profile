# Go footguns

The things Claude gets wrong by default on Go. Gotchas first; the cross-language
ones live in `gotchas.md`.

## Binary versioning

Every Go binary MUST support `--version` and inject at build time — never
hardcode. Pattern:

```go
// cmd/<name>/main.go
var Version = "dev"
// … flag.Bool("version", …) → fmt.Printf("%s %s\n", name, Version); os.Exit(0)
```

```bash
# justfile / mise task / Makefile
go build -ldflags="-s -w -X main.Version=$(git describe --tags --always --dirty)" \
  -o bin/<name> ./cmd/<name>
```

`git describe` gives `v1.2.3`, `v1.2.3-5-gabcdef`, or `dev` (fallback). `-s -w`
strips debug symbols for production builds. Never ship without `-ldflags`.

## Ruleguard custom-lint `rules/` dir

Every Go project gets a `rules/` directory; one file per rule:

```
rules/
├── doc.go                 # package gorules
├── time_now_outside_facade.go
└── direct_os_call.go
```

Rule file template:

```go
// Package gorules provides custom linter rules via ruleguard.
// Provides: Linter rule for <description>
package gorules

import "github.com/quasilyte/go-ruleguard/dsl"

func TimeNowOutsideFacade(m dsl.Matcher) {
    m.Match(`time.Now()`).Report("use timeSource.Now() — direct time.Now() breaks tests.")
}
```

Wire into golangci-lint:

```yaml
linters-settings:
  gocritic:
    enabled-checks: [ruleguard]
    settings:
      ruleguard:
        rules: "${configDir}/rules/*.go"
```

## Concurrency — never hardcode worker counts

```go
// ❌ arbitrary constant with no measurement behind it
maxWorkers := 10

// ✅ CPU-bound work
workers := runtimeinfo.DefaultWorkerCount()

// ✅ I/O-bound work (multiplier 2–4×)
workers := runtimeinfo.SuggestedConcurrency(4)
```

`runtimeinfo.DefaultWorkerCount()` is a intent-named wrapper around
`runtime.NumCPU()`. Naming it `NumCPU` in worker context says nothing about why
you're using it; naming it `DefaultWorkerCount` does.

## Parallel-test safety

Four rules, all enforced:

- `t.TempDir()` not shared paths — `TempDir` is test-scoped and auto-cleaned.
- `net.Listen("tcp", ":0")` not hardcoded ports — the OS picks a free port.
- No global mutable state accessed across parallel tests — race detector will
  catch it, but fix the design, don't just add a mutex.
- No `time.Sleep` for synchronization — use channels or `sync.WaitGroup`. If you
  need time comparisons in tests, assert with a tolerance
  (`assert.InDelta(t, expected, actual, 0.01)`), not `==`.

## `//nolint` discipline

`//nolint` is legal only for:

1. A confirmed linter bug — include the issue URL in the comment.
2. Generated code — add the directive in the generator template, not by hand.
3. A benchmarked performance optimization that the linter can't model.

Package-level `//nolint` (in `doc.go` or a build tag) is **forbidden**. It
silences the linter for the entire package, hiding real issues behind a blunt
override.

Every `//nolint` without a reason comment is a tech-debt marker with no
expiry — it rots silently. Format: `//nolint:lintname // reason: ...`

## Package-naming blacklist

These names are forbidden:

`common`, `utils`, `helpers`, `misc`, `shared`, `lib`

They name the _nature_ of the code (grab-bag), not what it _does_. A package
named `utils` will grow until it means nothing. Name for function:
`format`, `auth`, `billing`, `storage`, `validate`, `metric`.

The test: can you add a second package with a different responsibility but the
same name? If yes (`utils2`), your name is wrong.
