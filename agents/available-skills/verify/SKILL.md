---
name: verify
description: Use before declaring a change works — drive the running app/CLI/UI and assert the real end-state end-to-end. Don't report a change complete on a successful edit or a passing unit test alone. Load before saying done / working / fixed / verified. Also when the user says "look at the ui yourself", "Run it yourself", or "visual confirmation with chrome/firefox mcp".
---

# Verify

A successful edit is not evidence. A green unit test proves the _logic_, not that
the deployed thing does the right thing. This skill is a procedure, not a reminder —
run it the same way every time; don't improvise a spot-check.

> "Without a check it can run, 'looks done' is the only signal available, and you
> become the verification loop: every mistake waits for you to notice it."

## The procedure (run in order, every time)

1. **Decompose the claim.** List every named acceptance target as its own row —
   never a single blanket "verified." Five features named in the ask = five rows.
   A claim covering N targets with fewer than N observed rows is a defect in the
   report, not a shortcut.
2. **Build the evidence matrix.** For each row: observed end-state | observation
   method | fixture used | result | limits. Template + worked example:
   `references/evidence-matrix.md`. The matrix travels with the "done" report —
   it is the artifact, not a private scratch note.
3. **Check fidelity.** Name the property the target claims (color, latency,
   ordering, byte-exact output) and confirm the observation method can actually
   carry that property. An instrument that strips the property proves nothing
   about it — see the ANSI-stripped-capture case in the reference file.
4. **Check exercise.** Confirm real data (or a deliberately constructed fixture)
   actually drives the code path under test. A feature "verified" against a
   transcript that never contains the triggering condition never ran. If no real
   input exercises a target, build a synthetic fixture that does — a row with no
   input that reached the target stays unverified.
5. **Fresh-start every observation.** Rebuild/install, then observe a _newly
   started_ process or session — never a stale binary or a reused chat/tab. The
   binary on disk being current is not verification; the process you're looking
   at must have started after the rebuild. (Full drill: `agentmux-verify` skill.)
6. **Re-drive integrated end-to-end yourself.** A subagent's "done" is a claim,
   not evidence — per-worker green does not imply integrated green. Before
   accepting, run the real end-to-end path yourself on the merged/installed
   result.
7. **One live round-trip for config/credential/API changes.** A key, token, URL,
   or permission fix is only proven by one real call through the real service —
   config that "looks right" is not a substitute and has burned hours before.
8. **Sustain stateful claims.** "Draining," "recovering," "staying up" require
   sampling across an interval and confirming the trend holds — not one favorable
   reading. Two consecutive clean samples is the floor; more for anything that
   previously flapped.
9. **Downgrade on any gap.** If any row lacks an observation, fidelity check, or
   exercise: the claim for that target becomes "unverified: `<target>`" in the
   report. Silence about a gap is forbidden — an absent row is read as a lie, not
   an oversight.

Run the check → read the specific error → fix only that → rerun from the top.
Never accumulate fixes and verify once at the end. The loop closes when the check
is clean and stays clean across two runs (rule 8).

## Verification patterns by surface

- **Frontend/UI:** real dev server, open the real page, trigger the control
  directly, screenshot before/after, zero new console errors.
- **API/backend:** exercise the real endpoint against a running server; assert
  status AND body against a fixture; watch logs. See `scripts/verify-endpoint.sh`.
- **CLI:** run the actual command in a real shell (tmux if it needs a TTY); assert
  output, exit code, files written; run twice for idempotence.
- **Batch/destructive/multi-file:** `analyze → changes.json → validate_plan.py →
execute → verify` — validate the plan before it touches real state.
- **Fresh-context adversarial review:** spawn a read-only subagent briefed with
  only the goal + changed files (no prior context) to find what self-review can't.

## Live enforcement

`~/.claude/hooks/completion-gate.py` is a deployed Stop hook: it blocks any turn
whose final message contains a completion word (done/fixed/verified/working/...)
unless the recent transcript shows an evidence marker (tool result, exit code,
HTTP status, test PASS/FAIL) or the message already carries a downgrade phrase
("not yet verified", "should work", "untested"). Writing the report form below
satisfies it by construction — don't fight it with a vaguer claim.

## Quantitative exit conditions (prefer numeric thresholds — text gets gamed)

| Weak (gameable)  | Strong (machine-checkable)                                              |
| ---------------- | ----------------------------------------------------------------------- |
| "looks good"     | `exit code 0`                                                           |
| "tests pass"     | `go test ./... 2>&1 \| grep -c FAIL` = 0                                |
| "no errors"      | `grep -c "ERROR\|WARN" app.log` = 0                                     |
| "endpoint works" | `curl -s -o /dev/null -w "%{http_code}"` = 200 AND body matches fixture |

## Gotchas

- **Staging can lie.** A 200 is necessary, not sufficient — check downstream state.
- **Unit test ≠ live verification.** State which one you have.
- **Playwright/Puppeteer can't see native `alert()`/`confirm()`** — verify by hand.
- **Subagents inherit assumptions.** A validator briefed on full context shares
  your blind spots; fresh context is the point.
- **Flaky is a bug, not an edge case.** Run until consistently clean, not once.

## Verification report (output form)

```text
Verified: <N of M targets>
| target | observed end-state | method | fixture | result | limits |
|---|---|---|---|---|---|
| ...    | ...                 | ...    | ...     | PASS/FAIL | ... |

Unverified: <target> — <why: no observation / fidelity gap / no exercising input>
Evidence: <exact command/tool result each row cites>
```

State evidence and its limits with every claim: "Confirmed X, measured by Y,
sustained over Z" — or "Unit-tested; live effect NOT yet confirmed; watching for
W." A claim without its matrix attached is a guess wearing a lab coat.

## Scripts

`scripts/check-tests.sh` — Stop hook template: blocks turn-end until the test
suite passes. Superseded for completion-claim gating by the deployed
`completion-gate.py`; still useful as a repo-local test-only gate.

`scripts/verify-endpoint.sh` — curl with status + body assertion against a
fixture. Usage: `./scripts/verify-endpoint.sh <url> <expected-status> <fixture-file>`
