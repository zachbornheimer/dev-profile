# API Docs — Full Contract Reference

Source of truth: `~/.claude/rules/api-standards.md`. This file distills the
sections too long for SKILL.md.

---

## Response Envelope

Every successful response carries exactly these five fields at root. No exceptions.
No bare-array responses. No endpoint-specific shapes.

```json
{
  "object": "<resource_type>",
  "request_id": "req_01HZK2N5GQR9T8X4B6FJW3Y1AS",
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "livemode": true,
  "data": { ... }
}
```

- `object` — stable string discriminator; consumers switch on this, not URL path.
- `request_id` — server-minted ULID, format `req_<26-char-ulid>`.
- `idempotency_key` — echoes the `Idempotency-Key` header byte-identically; `null`
  for GETs on the allowlist.
- `livemode` — derived from credential, not request.
- `data` — resource payload (object) or list payload `{ data, has_more, next_cursor }`.

`BaseResponse` schema in `components.schemas`; every 2xx composes via
`allOf: [BaseResponse, { properties: { data: <ResourceSchema> } }]`.

---

## Idempotency

- Header: `Idempotency-Key` (UUID v4). Required on every mutating operation.
  Exempt: webhook receivers (provider `event.id` is the dedupe anchor).
- Echo the key in the response envelope.
- Replay window: 24 hours. Same key + same body → cached response. Same key +
  different body → `409 Conflict`, `code: idempotency_conflict`.
- Never in the URL. Never SHA-256-derived (collision risk on identical bodies).
- SDK auto-retries on 5xx/429 reuse the same key.

---

## Errors (RFC 7807)

Content-type: `application/problem+json`. Extended fields:
`code` (stable enum), `advice_code`, `param` (JSON-pointer for validation errors),
`request_id`, `doc_url`.

- `code` values are never renamed once shipped. Deprecated codes dual-write for ≥ 6
  months alongside replacement.
- Match on `code`, not HTTP status or message text.
- Every code has: one HTTP status (1:1), one-line meaning, one-line remediation.
  Document as a table in `guides/errors.md`.

---

## Pagination

Cursor-based only. No offsets, no page numbers.

- Cursor: opaque base64. Clients never decode, construct, or inspect.
- Params: `cursor` + `limit`. Default 25, max 100.
- Response: `{ data, has_more: bool, next_cursor: string|null }`.
  `next_cursor` is `null` iff `has_more` is `false`.
- SDK surface: `.list().autoPagingEach()` async iterable;
  `.list().autoPagingToArray({ limit: N })` eager-drains with mandatory max-item cap.

---

## Spectral Rules

### Enable

| Rule                                                  | Severity | Why                                                                                                          |
| ----------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------ |
| `operation-description-present` (built-in)            | warn     | Every op has a description; min 80 chars                                                                     |
| `operation-summary-length` (custom, max 80)           | warn     | Left-rail label length                                                                                       |
| `no-additional-properties-true` (custom)              | warn     | Type closure; allowlist only Metadata                                                                        |
| `mutation-requires-idempotency-key` (custom)          | warn     | Exempt `/webhooks/*` and non-versioned legacy                                                                |
| `prose-no-banned-phrases` (custom)                    | warn     | "please note", "in order to", "utilize", "leverage", "subsequent", "prior to", "regarding", "may optionally" |
| `prose-readability-grade` (custom, warn=14, error=20) | warn     | Stripe scores 12–14; FK≤10 is impossible on technical prose                                                  |
| `error-response-uses-problemdetails` (custom)         | error    | Every 4xx/5xx → ProblemDetails                                                                               |
| `response-envelope-shape` (custom)                    | error    | Every 2xx schema declares the 5 envelope fields                                                              |
| `pagination-cursor-only` (custom)                     | error    | Accept `cursor`+`limit`; reject `page`/`offset`/`starting_after`                                             |
| `operation-tags-required` (built-in)                  | error    | Renderer nav                                                                                                 |
| `money-field-is-integer` (custom)                     | error    | Minor units only; never floats                                                                               |
| `version-prefix-required` (custom)                    | error    | Every new path starts `/vN/`                                                                                 |

### Do NOT enable

| Rule                                                         | Why it's wrong                                                                                                 |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `operation-prose-template`                                   | Duplicates what OpenAPI fields already carry; makes every page identical and clinical. Stripe doesn't do this. |
| `operation-summary-imperative` (≤ 6 words, whitelisted verb) | Artificially terse. "Create an account link" beats "Create accountlink".                                       |
| `prose-readability-grade` with `warnAt: 10`                  | Impossible on technical domain prose.                                                                          |

---

## Webhooks

- Signing: HMAC-SHA256 of `<timestamp>.<raw body>`. Header: `{Brand}-Signature: t=<ts>,v1=<hex>`.
- 5-minute timestamp tolerance window.
- At-least-once delivery. De-dupe on `event.id`.
- Retry: exponential backoff, 7 attempts over 24 hours.
- Receivers exempt from `Idempotency-Key`.
- Always document a constant-time verifier (never a naive string compare).

---

## CI Gate Contract

Order: Spectral lint → generator tests → public-spec drift check → SDK generation
smoke (go build / tsc --noEmit / python -m compileall) → openapi-diff (breaking
change requires `BREAKING:` commit prefix) → changelog drift.

Production: `rdme openapi upload` + `rdme docs upload`. Per-PR previews to
`pr-<N>` slug.

---

## Persona Discipline

Pick a stable fake-data set and use it everywhere. Recognition compounds.
Define the set at project start in `guides/personas.md`.

---

## Enum Documentation Pattern

```yaml
type:
  type: string
  enum: [individual, company, government_entity, non_profit]
  x-enum-descriptions:
    individual: A single named human applicant.
    company: A for-profit organization.
    government_entity: Federal, state, tribal, or local government.
    non_profit: A 501(c) organization.
```

Consider `x-stripeBypassValidation: true` where forward-compatibility matters.
