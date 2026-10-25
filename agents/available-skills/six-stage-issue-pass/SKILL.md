---
name: six-stage-issue-pass
description: Use when a bug, complaint, or feedback item is reported (by the owner, a carrier, a teammate, or a tracker like Linear) and must be turned into durable program work — an inventory row, a written 6-stage assessment, and a red verification test that reproduces the issue as the user observes it. Also use when auditing an external bug list against an existing fix program. Not for executing fixes (that's the batch/fix flow) — this is intake, root-cause framing, and class prevention.
---

# Six-Stage Issue Pass

Every reported issue goes through six stages, **in writing**, before anyone fixes
anything. The output is three artifacts: an inventory row, a ticket
(`assessments/TICKET-NNNN.md`), and a verification test proven red for the
described reason. A problem stated once must never need stating twice — the red
test IS the work queue entry.

## The six stages (each is a section of the ticket)

1. **What was said.** The reporter's words, verbatim. Quote the original
   complaint — never paraphrase from memory. Screenshots/links included.
2. **What it means.** The interpreted _user-visible contract_ — one sentence a
   user would recognize ("the premium shown never drops the dollar sign"), not
   an implementation statement. This sentence becomes the test title.
3. **COULD it be systemic.** Enumerate the defect _classes_ that could produce
   the symptom (state-ordering, coerced-absent values, dual-source-of-truth,
   cascade/layer conflict, stale generated artifact…). Think before looking.
4. **DOES it manifest systemically.** Go read the actual code/artifacts and
   determine which class it IS, with evidence (file:line, probe output, trace).
   The divergence point, not the consequence.
5. **Catch it elsewhere.** Where else does this class bite _today_? Sweep
   mechanically — derive the candidate set from the DOM/schema/artifact itself
   (a crawler, a grep over generated output), never a hand-list. Each hit
   becomes its own inventory row linked back to this one.
6. **Prevent the class.** The structural guard that makes recurrence
   impossible: a lint/check script, a primitive that replaces the hand-rolled
   pattern, a type that can't express the invalid state. Name it even if it
   lands in a later batch.

## Filing conventions

- **Location:** program artifacts live at
  `~/.local/share/ai-artifacts/<program-slug>/` — personal records, never
  committed to a code repo. (Verification tests are the exception: they always
  live in the repo they test.) Honor an existing program's established
  location rather than relocating it mid-flight.
- **Inventory:** `inventory.jsonl` is the source of truth — append-only, one
  JSON object per issue (id, description, sources, tests, overlaps, layer,
  status), so parallel filing agents never conflict. A rendered
  `MASTER-INVENTORY.md` table view is generated from it (columns: Issue-ID |
  Description | Source(s) | Reproducing test(s) or NONE | Overlaps with |
  Layer). IDs are stable and sequential (`MI-NNN` style).
- **Layer** = where the issue is genuinely _observed_ (browser/playwright,
  pipeline/pytest, pdf, harness, shell-ci) — not where the fix will land.
- **Ticket:** `assessments/TICKET-NNNN.md`, sections 1–6 above plus a verdict.

## Verification tests — not inference tests

- The test must reproduce the issue **as the reporter observes it**. Asserting
  an artifact contains a string, that code is "renderable", or an adjacent
  behavior is an inference test — rejected.
- Title = the stage-2 contract, derived from the complaint's own words.
- Assertions = user-observable evidence (rendered text, computed styles, real
  navigation), at the row's observation layer.
- **Verify the verifier:** run the red and confirm it fails _for the described
  reason_ — the failure output must show observed-vs-expected user-visible
  state. Paste that output into the ticket. A red that fails for a harness
  reason is not a repro.
- For already-fixed issues, prove the test by temporarily reverting the fix
  (git stash) and showing the red.

## Hard rules

- **No waivers, ever.** There is no "waived/expected-red" category; an
  unfixable-today item is KNOWN-OPEN work with a standing red.
- **Red tests are the dispatch queue.** New reports fold INTO the queue; they
  don't preempt standing reds of similar severity. Report queue state as
  reds-remaining, not fixes-shipped.
- **Once, not twice.** If a reporter re-describes a problem you already have,
  the intake failed — find why the existing row/test didn't cover the variant
  and file the gap as its own row.

## Auditing an external bug list (tracker import)

For each external issue (Linear, carrier email, transcript): quote it (stage 1),
then judge it against the existing program — does a landed or in-flight fix
plausibly resolve it? If yes: record `resolved-by-<row>` with evidence (commit,
green run — ideally a quick local repro attempt). If no: full six-stage pass and
a new row. Keep the audit map as its own document (issue → verdict → evidence).
