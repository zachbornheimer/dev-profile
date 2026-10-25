---
name: status-report
description: Use when the user types /status-report, asks for a status update on long-running or overnight work, or when reporting after a loop, schedule, autonomous run, or handoff. Produces an evidence-based, ticket-first status report from strict JSON and renders it as a compact colorized terminal table with per-ticket verification checks.
---

# Status Report

Produce a ticket-first status report. The model determines facts and semantic state; the renderer determines colors, spacing, symbols, and table layout.

## Output contract

Every reportable item must appear exactly once in `issues`.

- Use the real issue or ticket ID when one exists.
- Never invent a tracker ID.
- If no ticket exists, use `UNTRACKED-<n>` for this report and set `needsTicket: true`.
- Do not create free-floating `PROBLEMS`, `DIRECTIVES`, `DEFERRED`, or `WATCH` sections.
- Represent those concerns on the relevant issue instead.
- Keep each issue summary to one decision-useful sentence.
- Put detailed verification in `checks`.
- Every check requires evidence.
- Do not report tokens, turns, agents, retries, tool calls, or elapsed effort unless that activity is itself the problem.

The JSON must conform to [schema/report.schema.json](schema/report.schema.json).

## Procedure

1. Establish the reporting window and effort name.
2. Read the durable project goals when available.
3. Review actual results from the current run.
4. Check hook or automation logs only when relevant to a reported claim.
5. Reconcile the work into ticket-sized issues.
6. Verify positive claims directly. Downgrade anything unproven to `warn`.
7. Write the report JSON to a temporary file.
8. Render it with the bundled renderer.
9. Return the rendered report, not the raw JSON, unless the user asks for JSON.

Use the renderer rather than hand-formatting terminal output:

```bash
./scripts/render.sh /path/to/report.json
```

Equivalent:

```bash
go run ./scripts/render.go /path/to/report.json
```

Before first use, check that Go is available:

```bash
command -v go
```

The renderer requires Go 1.22 or newer. Do not install Go silently. If it is missing, tell the user. On macOS, `brew install go` is an appropriate installation option.

## Issue states

Use exactly one:

- `investigating` — cause or scope is still being established.
- `in_progress` — implementation or verification is underway.
- `pr_created` — a PR exists but has not landed.
- `blocked` — a confirmed blocker prevents progress or completion.
- `done` — the relevant completion criteria are proven.
- `deferred` — work is intentionally staged for later.
- `needs_ticket` — the work is real but has no durable tracker issue yet.

Do not mark an issue `done` merely because code was written or a PR merged. Use the user's declared completion condition. If production proof is required, `done` requires production proof.

## Check statuses

Use exactly one:

- `pass` — directly proven.
- `warn` — incomplete, degraded, or not yet proven.
- `fail` — a required condition is confirmed false.
- `blocked` — the check cannot complete because of a confirmed dependency.
- `hold` — deliberately staged and not currently expected to complete.

Prefer lifecycle checks when they apply:

1. `Issue hypothesis`
2. `Issue replicated`
3. `Fix implemented`
4. `Fix verified in testing`
5. `PR landed`
6. `Fix proven in prod`

Omit irrelevant lifecycle stages. Add domain-specific checks when they improve the decision.

## Evidence

Each check must contain at least one evidence string.

Good evidence includes:

- qualified issue or PR IDs such as `zyins#755`;
- commit SHAs;
- test names and results;
- CI or Actions runs;
- logs;
- measured counts with their source;
- observed tracker state;
- durable goal entries.

Prefer compact evidence. Do not paste logs into the report.

A claim without direct proof must be phrased as unproven and use `warn`.

## Verdict

Do not write the verdict into the JSON. The renderer derives it:

- `NO-GO` — any issue is `blocked`, or any check is `fail` or `blocked`.
- `AT RISK` — otherwise, any issue is `investigating`, `in_progress`, `pr_created`, or `needs_ticket`, or any check is `warn`.
- `GO` — otherwise.

`deferred` and `hold` are neutral when they are intentional and do not violate the declared outcome.

## Rendering

The terminal renderer owns presentation.

- Summary table first: `ISSUE`, `STATE`, `SUMMARY`.
- Then one section per issue.
- Green `✔` for `pass`.
- Yellow `!` for `warn`.
- Red `✘` for `fail` and `blocked`.
- Dim `–` for `hold`.
- State labels are colored by severity.
- Section headings use cyan.
- Evidence is dim.
- ANSI color is automatic on a TTY and disabled for redirected output or `NO_COLOR`.
- `--color=always` and `--color=never` override detection.

Keep the model out of layout decisions. Never embed ANSI escapes, spacing instructions, or terminal-width assumptions in the JSON.

## Example

See [examples/zys-1540.json](examples/zys-1540.json).

## Verification

After changing this skill or renderer, run:

```bash
./tests/test.sh
```

The test verifies parsing, semantic validation, ANSI output, plain output, verdict derivation, and rejection of invalid reports.
