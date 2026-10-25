---
name: status-report
description: Use when the user types /status-report, asks for a status update on long-running or overnight work, or when reporting after a loop, schedule, autonomous run, or handoff. Produces an evidence-based, ticket-first report from strict JSON and renders it as compact Cargo/Brew-style ANSI terminal output. Every issue is summarized in a table and expanded into evidence-backed progress checks using only Done, In Progress, or Not Started.
---

# Status Report

Produce a ticket-first progress report. The model supplies facts and check state. The bundled renderer derives issue/report state and owns colors, symbols, sorting, wrapping, and layout.

## Core contract

Every reportable work item must be tied to an issue or ticket and appear exactly once in `issues`.

- Use the real issue/ticket ID when one exists.
- Do not invent tracker state from activity.
- Do not create free-floating `PROBLEMS`, `DIRECTIVES`, `DEFERRED`, or `WATCH` sections.
- Do not use `deferred`, `blocked`, `warn`, `hold`, `investigating`, `pr_created`, `needs_ticket`, or any other state.
- The only allowed progress states anywhere in the report are:
  - `done`
  - `in_progress`
  - `not_started`
- Every issue must contain at least one explicit progress check.
- Keep the issue summary to one decision-useful sentence.
- Put verification detail and evidence in `checks`, not in the summary.
- Do not report turns, tokens, agents, retries, tool calls, or elapsed effort unless that activity is itself the user-visible problem.

The JSON must conform to [schema/report.schema.json](schema/report.schema.json).

## State semantics

Use the states literally.

### `done`

The named check is directly proven complete.

Examples:

- a reproduction actually succeeded;
- the patch is merged;
- the production behavior was re-verified successfully.

Do not use `done` because a ticket moved to Done, code exists locally, or somebody said it should work.

### `in_progress`

The named check has materially started but is not complete.

Examples:

- a PR exists and is awaiting merge;
- a reproduction is actively narrowed but not yet confirmed;
- production verification is currently running.

Do not use `in_progress` merely because Linear says `Ready for Dev` or `In Progress`. The status describes the check named in this report, not the tracker's workflow column.

### `not_started`

The named check has not begun or has no evidence of beginning.

Examples:

- no live reproduction was attempted;
- no patch exists;
- production was not re-verified.

A dependency may be described in `detail`, but dependency language does not create a fourth state.

## Derived issue state

Do **not** put an issue-level `state` in the JSON. The renderer derives it from checks so issue and evidence cannot contradict each other:

- all checks `done` -> **DONE**;
- all checks `not_started` -> **NOT STARTED**;
- any other mixture -> **IN PROGRESS**.

The report status is derived the same way from its issue states.

This means an issue with a merged PR but no production verification is **IN PROGRESS**, not Done.

## Procedure

1. Establish the reporting window and effort name.
2. Read durable project goals when available.
3. Review actual results from the reporting window.
4. Check hook/automation logs only when relevant to a claim.
5. Reconcile all reportable work to issue/ticket IDs.
6. For each issue, identify the progress checks that determine whether the issue is actually complete.
7. Assign each check exactly one of `done`, `in_progress`, or `not_started` based on direct evidence.
8. Construct one JSON object matching the schema **in memory**.
9. Do not write a temporary report file merely to render it.
10. Pass the JSON object directly to the renderer with `--json`.
11. Return the rendered report, not the raw JSON, unless the user asks for JSON.

## Checks

Use short, outcome-oriented check names. Prefer these lifecycle checks when relevant:

1. `Issue hypothesis`
2. `Issue replicated`
3. `Fix implemented`
4. `Fix verified in testing`
5. `PR landed`
6. `Fix proven in prod`

Omit genuinely irrelevant stages. Do not omit the next unmet stage merely to make the report look healthier.

Each check must include:

- `name` — what condition is being evaluated;
- `status` — `done`, `in_progress`, or `not_started`;
- `detail` — what is true now;
- `evidence` — at least one concrete source.

A line such as "Accepted out of Triage; Agent Quoter not walked live" is **not** a completed reproduction. Represent it as:

```json
{
  "name": "Issue replicated",
  "status": "not_started",
  "detail": "Agent Quoter has not been walked live, so the reported behavior is not yet reproduced.",
  "evidence": [
    "Linear SAH-9395 status=Ready for Dev; no live Agent Quoter verification in this reporting window."
  ]
}
```

## Evidence

Every check requires evidence.

Useful evidence includes:

- qualified issue or PR IDs such as `zyins#755`;
- commit SHAs;
- test names/results;
- CI or Actions runs;
- logs;
- measured counts and their source;
- observed tracker state;
- durable goal entries.

Prefer compact evidence. Do not paste raw logs.

Tracker state is evidence, not proof of application behavior. For example, `Linear SAH-9395 status=Ready for Dev` proves only the tracker state.

## Rendering

The renderer owns presentation and should make the report scannable before the details are read.

### Summary

Render every issue in one table:

```text
ISSUE       STATUS        SUMMARY
```

Sort issues:

1. **IN PROGRESS**
2. **NOT STARTED**
3. **DONE**

Use only semantic colors:

- **green** = Done
- **blue** = In Progress
- **red** = Not Started

Do not use cyan/yellow for competing semantic states.

### Detail sections

Repeat the derived state directly beside every issue ID:

```text
SAH-9395  NOT STARTED
NQ Accidental Death quotes are still Ready for Dev.

✘ Issue replicated  NOT STARTED
    Agent Quoter has not been walked live, so the behavior is not reproduced.
    ↳ Linear SAH-9395 status=Ready for Dev; no live Agent Quoter verification this window.
```

Markers are deterministic:

- green `✔` = Done
- blue `●` = In Progress
- red `✘` = Not Started

Color both the marker/check name and its explicit state label. Keep detail text normal and evidence dim.

## Invocation

Preferred agent invocation:

```bash
uv run ./scripts/render.py --json '<REPORT_JSON>'
```

Force color when the calling harness is not attached to a TTY:

```bash
uv run ./scripts/render.py --color=always --json '<REPORT_JSON>'
```

The renderer also accepts stdin or a path for human/manual use:

```bash
printf '%s' "$REPORT_JSON" | uv run ./scripts/render.py --stdin
uv run ./scripts/render.py ./examples/zys-1540.json
```

The renderer is Python 3.11+ and stdlib-only. `uv` manages execution; no Python packages are required.

Before first use:

```bash
command -v uv
```

Do not install `uv` silently. If it is missing, tell the user. On macOS with Homebrew, `brew install uv` is appropriate.

## Example JSON

```json
{
  "version": 2,
  "effort": "BPP / zyins ops",
  "summary": "SAH-9395 has not been reproduced live yet.",
  "issues": [
    {
      "issueId": "SAH-9395",
      "summary": "NQ Accidental Death quotes are still Ready for Dev.",
      "checks": [
        {
          "name": "Issue replicated",
          "status": "not_started",
          "detail": "Agent Quoter has not been walked live, so the reported behavior is not yet reproduced.",
          "evidence": [
            "Linear SAH-9395 status=Ready for Dev; no live Agent Quoter verification in this reporting window."
          ]
        }
      ]
    }
  ]
}
```

See [examples/zys-1540.json](examples/zys-1540.json) and [examples/sah-9395.json](examples/sah-9395.json).

## Verification

After changing this skill or renderer, run:

```bash
uv run ./tests/test.py
```

The smoke test verifies inline JSON input, strict three-state validation, rejection of `deferred`, derived issue/report state, repeated detail status, and green/blue/red ANSI output.
