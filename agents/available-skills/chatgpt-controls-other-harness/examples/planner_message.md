# LOCAL RUN REQUEST

## Operation

Targeted repair + deterministic proof

## Ticket / correlation

Ticket: EXAMPLE-123
Repo: /Users/me/Developer/example
Maturity target: structurally_hardened

## Goal

Move local workspace mechanics behind a consumer-owned workspace port without changing product behavior.

## Acceptance

- Product workflow imports no concrete workspace adapter.
- Cancellation reaches local subprocesses.
- Existing multi-worker behavior remains covered.
- Focused tests, full tests, vet, and diff-check pass.

## Constraints

- Preserve all current uncommitted work.
- Do not commit/push/merge/reset/clean.
- Use bounded waits/timeouts.
- Deterministic verification before semantic verification.
- Package evidence even on failure.
- Runner process exits 0 after packaging; report.json carries internal outcome.
- Emit one downloadable runner file with a fresh UUID.

## Known baseline failures

- None known.

## Prior evidence

The representative happy path is green. The remaining gap is the ownership boundary.

## Requested action

targeted repair

## Stop conditions

- Stop when acceptance is proved.
- Do not broaden into adjacent work.
