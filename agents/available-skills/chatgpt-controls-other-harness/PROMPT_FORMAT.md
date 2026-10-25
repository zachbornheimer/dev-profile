# Planner → Runner Prompt Format

This is the recommended task envelope to give the cloud planner. It is intentionally plain Markdown so it works across agents.

## Template

```md
# LOCAL RUN REQUEST

## Operation

<short operation name>

## Ticket / correlation

Ticket: <optional ticket id>
Repo: <absolute local repo path if known>
Base SHA: <optional expected SHA>
Maturity target: <prototype | structurally_hardened | production_verified>

## Goal

<one paragraph describing the desired repository state>

## Acceptance

- <observable criterion>
- <observable criterion>
- <observable criterion>

## Constraints

- Preserve all current uncommitted work.
- Do not commit/push/merge/reset/clean.
- Use bounded waits/timeouts.
- Deterministic verification before semantic verification.
- Package evidence even on failure.
- Runner process exits 0 after packaging; report.json carries internal outcome.
- Emit one downloadable runner file with a fresh UUID.

## Local capabilities

- Python: <version/path if relevant>
- Go/Rust/etc: <if relevant>
- zq: <path if relevant>
- coding harness: <claude/codex/etc if relevant>

## Known baseline failures

- <known baseline failure, or "none known">

## Prior evidence

<short factual summary of what is already proved and what concrete gap remains>

## Requested action

<implementation | proof-only | source snapshot | targeted repair | experiment>

## Stop conditions

- Stop when acceptance is proved.
- Do not broaden into adjacent tickets/features.
- If blocked by a missing local capability, report it rather than inventing a substitute.
```

## What the planner should return

During the automated controller loop, the planner returns:

```text
run-<fresh-uuid>.py
```

as one downloadable artifact.

The runner itself should encode the request it is executing inside its evidence (`request.json` or a request text file) so later reviewers can reconstruct intent from the ZIP.

## Request JSON

For machine-readable logging, a runner may also write:

```json
{
  "schema_version": 1,
  "run_id": "00000000-0000-4000-8000-000000000000",
  "ticket": "EXAMPLE-123",
  "operation": "targeted-repair",
  "repo": "/absolute/path/to/repo",
  "maturity_target": "structurally_hardened",
  "goal": "Move worktree mechanics behind a consumer-owned workspace port.",
  "acceptance": [
    "Product workflow imports no concrete ZQ adapter",
    "Cancellation reaches local ZQ process",
    "Focused and full tests pass"
  ],
  "constraints": {
    "preserve_uncommitted_work": true,
    "allow_commit": false,
    "allow_push": false,
    "allow_merge": false,
    "allow_reset": false,
    "allow_clean": false
  }
}
```
