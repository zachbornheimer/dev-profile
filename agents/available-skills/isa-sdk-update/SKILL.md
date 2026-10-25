---
name: isa-sdk-update
description: Use when rolling ANY change through the ISA SDK (isa-sdk / @software-automation-holdings/isa-sdk) — the contract-first order across isa-platform's five language packages, the mirror/vendoring traps, per-language toolchain gotchas, and the release checklist.
---

# ISA SDK Update

## Where the code actually lives (the trap that wastes a session)

- The public GitHub repo `Software-Automation-Holdings-LLC/sdk` is a **generated
  mirror** (ADR-035). Its `mise test` runs ZERO tests by design. Never edit it —
  edit **`Software-Automation-Holdings-LLC/isa-platform`**: `packages/{go,ts,python,php,csharp}`,
  services under `services/`, contracts under `shared/schemas/` + `docs/internal/`.
- The public OpenAPI bundle `shared/schemas/gen/openapi/openapi-public.yaml` is
  **vendored from the zyins repo** (`go/zyins/api/openapi-public.yaml`, see
  `MANIFEST.json`). Hand-editing it trips `scripts/verify-public-openapi.mjs`
  (sha256 drift guard). Endpoint additions to the public spec go in **zyins**,
  then `make refresh-public-openapi` here.
- Session/auth wire contract has no OpenAPI/proto home: the canonical spec is
  `docs/internal/authentication-advanced.md` + the byte-exact fixture
  `tests/conformance/fixtures/auth-vector.json`. Protos (`shared/schemas`, buf)
  cover connect services + events only; `events/session/v1` is the eApp
  analytics event — a DIFFERENT concept from auth sessions. Don't invent a proto
  for a REST-only endpoint.

## The order that works (contract-first, outside-in)

1. **Server handler red-first** (`services/account/...` etc.): add the failing
   assertion against current behavior, capture red, change, green.
2. **Contract doc** (`docs/internal/*.md`) — fix drift while you're there (e.g.
   the doc advertised `POST /v1/sessions/refresh`; the real route is a
   `POST /v1/sessions` re-issue that rotates in place with a 30s grace overlap).
3. **Languages, one at a time, identical semantics + parallel naming**:
   Go → TS → Python → PHP → C#. All five share the SessionStore / interceptor
   shape; TS reference impl for bootstrap bytes is
   `packages/ts/src/core/internal/auth/bootstrap.ts`. Red-first per language:
   write the behavior test against the existing code, watch it fail, port the
   same policy, run that package's full suite.
4. **Docs/guides** (`api/guides/` renders to docs.isaapi.com — jr-dev clarity).
5. **Skill/report**: enumerate anything you left per-language.

## Per-language toolchain gotchas (all real)

- **Go**: module roots `packages/go` (imports as `github.com/...-LLC/sdk`) and
  each `services/<name>`. Plain `go test ./...` works.
- **TS**: `packages/ts`, vitest. `npx vitest run tests/<area>/<file>.test.ts`;
  full suite ~50s. Check `PUBLIC_API.txt` when adding exports.
- **Python**: no global pytest — run `uv run --with pytest -m pytest tests/ -q`
  from `packages/python`, then **`git checkout -- uv.lock`** (uv rewrites it).
  Known pre-existing failure on clean main:
  `tests/zyins/test_concurrency.py::test_100_parallel_asyncio_gather_distinct_request_ids`.
- **PHP**: `composer install` then `vendor/bin/phpunit --no-coverage`. The
  `Clock` interface needs BOTH `now()` and `nowMilliseconds()` on fakes.
- **C#**: NuGet.config expects `/tmp/isa-sdk-localfeed` to EXIST (`mkdir -p` it),
  and tests target net8.0 while the Mac has only .NET 10 — run
  `DOTNET_ROLL_FORWARD=LatestMajor dotnet test tests/Isa.Sdk.Tests.csproj`.

## Cross-SDK invariants (don't let one language drift)

- Bootstrap HMAC bytes are pinned by the auth-vector fixture — all five SDKs
  must produce identical hex. Adding a field to the bootstrap body is a wire
  break (major bump + doc + fixture).
- Session policy lives in named constants mirrored across languages
  (e.g. renew-after-age 30m / server bootstrap TTL 90m). Change them together
  or not at all.
- 401 handling: `session_expired` → renew + retry exactly once (safe for POSTs
  because `shared/go/auth/session/verifier.go` rejects pre-flight);
  `session_revoked` → terminal, never retried.

## Release (report, don't improvise)

- Bump `go/VERSION` **and** the csproj version before tagging (TS/Py/PHP derive
  from the tag). Tags `sdk/<product>/v*` auto-publish the mirrors — the mirror
  repo is never pushed to by hand. Never publish from a feature branch.
