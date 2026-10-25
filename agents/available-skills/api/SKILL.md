---
name: api
description: Use when CREATING, MAINTAINING, or UPGRADING an API (REST endpoints, an openapi spec, or `api/guides/`). Contract-first and Spectral-enforced. For the OpenAPI spec/docs structure itself, this pairs with the `api-docs` skill.
---

# API (contract-driven lifecycle)

The **contract is the source of truth**, not the implementation. The spec is
written first, linted (Spectral), and SDKs are _generated_ from it — never
hand-written. If the spec and the implementation disagree, the implementation has
the bug. Pick your mode below; the conventions and the linter gate apply to all
three. Full spec/doc structure lives in the `api-docs` skill — reference it, don't
duplicate it.

## Non-negotiable conventions (all modes)

- **Paths:** kebab-case, RESTful resources, versioned in the path (`/v1/`). Default
  to kebab-case unless a resource name forces otherwise.
- **Idempotency:** `Idempotency-Key` header (UUID v4) required on every mutating op
  (POST/PUT/PATCH/DELETE); echoed in the response envelope. Never in the URL.
- **Response envelope:** every 2xx carries the five fields — `object`, `request_id`,
  `idempotency_key`, `livemode`, `data`. Never a bare array at root.
- **Pagination:** cursor-based only (`cursor` + `limit`, `has_more`/`next_cursor`).
  Never page/offset.
- **Errors:** RFC 7807 `application/problem+json` with a stable `code` enum.
- **Money:** integer minor units, never floats.
- **Auth:** explicit `security[]` on every op (`[]` for public); credentials in
  headers, never query strings.

## CREATE — contract-first

1. Design the OpenAPI spec FIRST: resources, the conventions above, `x-codeSamples`.
2. **Lint the spec with Spectral** (the ruleset) — this is the gate; a red spec
   doesn't ship. `mise run lint` runs it in CI.
3. Generate the SDK/types from the spec (openapi-generator). Never hand-write them.
4. Implement to the contract; verify the running endpoint against the spec (`verify`).
5. Version from day one (`/v1/`), date-based `info.version`.

## MAINTAIN — additive-only

- Add fields / endpoints / enum values. **Never remove, rename, or retype** an
  existing field — that's a breaking change (→ UPGRADE).
- Every change re-lints Spectral and regenerates SDKs. The envelope + idempotency +
  pagination invariants must still hold.
- `code` values in the error enum are never renamed once shipped (dual-write a
  deprecated code ≥ 6 months alongside its replacement).

## UPGRADE — breaking, side-by-side

- Breaking change ships as a NEW major in the path (`/v2/`). Run `/v1` and `/v2`
  side-by-side for ≥ 6 months.
- Old major gets `Deprecation` + `Sunset` response headers (RFC 8594) and a
  migration guide.
- Changelog is generated from `x-version-history` blocks, not hand-written; CI fails
  on drift. `openapi-diff` gates the change (breaking → `BREAKING:` commit prefix).

## Gotchas

- Don't discriminate a `oneOf` by an INTERNAL taxonomy (product family, tier) — it
  breaks every consumer the day you add a value. Use a flat closed shape with
  optional fields; new families ship as value changes, not type changes.
- Don't document an operation the server doesn't actually honor (spec-side ≠
  server-side = 401s and tickets). Advertise only what's implemented.
- `additionalProperties: false` on request bodies (allowlist `Metadata` only).
- The spec is CI-gated: Spectral lint + generated-SDK smoke-build + `openapi-diff`
  breaking-change check. Contract-driven means the linter is the reviewer.
