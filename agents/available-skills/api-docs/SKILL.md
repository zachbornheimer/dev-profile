---
name: api-docs
description: Load before editing openapi*.yaml, openapi*.json, *.openapi.*, anything under api/guides/, or any Spectral ruleset. The OpenAPI documentation contract — not API design (see ux/ for errors, idempotency, versioning).
---

# API Docs

North star: [Stripe API Reference](https://docs.stripe.com/api) (rendered) and
[stripe/openapi](https://github.com/stripe/openapi) (source). A rule that
contradicts what Stripe's spec actually does is wrong — update the rule first.

## Gotchas — the traps that cost hours

**No multi-heading templates inside operation descriptions.**
`**What:** / **When to use:** / **Auth:** / **Errors:**` on every operation = a
wall of bold paragraphs that signals lint-driven, not hand-crafted. Stripe's
operation descriptions are 1–3 sentences of flowing prose. Auth is in `security[]`.
Errors are in `responses[]`. If you're writing a Spectral rule called
`operation-prose-template`, stop.

**No guide prose in `info.description`.**
Stripe's `info.description` is one sentence. Onboarding, auth narrative, glossary,
idempotency rationale — all go in `api/guides/*.md`, not the spec. Most renderers
show `info.description` only on the landing page; it hides from anyone who
navigates to an endpoint.

**Cursor-only pagination. No offsets. No page numbers.**
Inserts and deletes shift page boundaries under the caller. Params: `cursor` +
`limit`. Response: `{ data, has_more, next_cursor }`. Default limit 25, max 100.
Reject `page` / `offset` / `starting_after`.

**No credentials, PII, or identifiers in query strings.**
They land in CDN logs, browser history, and Referer headers. Auth goes in headers.
Use opaque IDs in paths. POST bodies for lookup-by-identity.

**`additionalProperties: false` is the default on request schemas.**
Unexpected fields are bugs. `additionalProperties: true` is only legal for the
`Metadata` schema (user-defined key-value bag). Never leave it unset on request
bodies.

**Stripe gut-check before calling done.**
Side-by-side compare your endpoint against
`https://docs.stripe.com/api/v2/core/accounts`. More bold headings than Stripe?
Prose in `info`? No code samples on every endpoint? Can't reach the full error
catalog in two clicks? Not done.

## Hub-and-spoke model (non-negotiable)

- **Reference surface** — the OpenAPI spec. Schemas, parameters, responses.
- **Guides surface** — `api/guides/*.md` for long-form prose.

Both ship in CI. Reference-only = wall of tables. Guides-only = no machine
contract.

## Operation anatomy (quick reference)

```yaml
post:
  operationId: createAccountLink # camelCase verb-noun (per ADR-009)
  summary: Create an account link # ≤ 80 chars, readable verb phrase
  description: |
    Creates an AccountLink … 1–3 sentences, no bold headings.
  tags: [AccountLinks]
  security: [...] # always explicit; [] for public-no-auth
  parameters:
    - $ref: "#/components/parameters/IdempotencyKey"
  responses:
    "200": { ... }
    default:
      $ref: "#/components/responses/Error"
  x-codeSamples:
    - { lang: curl, source: "..." }
    - { lang: go, source: "..." }
```

Code samples are mandatory on every public operation. `curl` first, always.

## Cross-cutting components — define once, `$ref` everywhere

`IdempotencyKey`, `Version`, `Cursor`, `Limit` in `components/parameters`.
`ProblemDetails`, `BaseResponse`, `Metadata`, `PageInfo` in `components/schemas`.
Every 2xx response composes via `allOf: [BaseResponse, ...]`.

## Full contract detail

See `references/contract.md` for: response envelope shape, idempotency spec,
Spectral rules table (+ which rules NOT to enable), webhook signing, versioning,
CI gate contract, persona discipline, enum documentation pattern.

Source: `~/.claude/rules/api-standards.md`
