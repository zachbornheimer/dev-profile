---
name: ui-decompose
description: Exhaustively decomposes a UI design source into an implementation-neutral, schema-validated specification, then requires fresh independent adversarial audits before emitting the final Markdown. Use before UI-kit mapping or implementation when omissions are unacceptable.
compatibility: "Claude Code v2.1.196+; Python 3 with jsonschema; source-specific MCP/browser tools as required"
argument-hint: "<design implementation prompt, path, URL, or attachment>"
disable-model-invocation: true
---

# UI Decompose

Turn the supplied design request into an exhaustive UI specification. Do not implement the UI. Do not map to a target UI kit.

The machine-readable decomposition is the source of truth. The final Markdown may be generated only after deterministic validation and a fresh adversarial reviewer both pass.

## Certification boundary

This skill makes completeness **enforceable as a workflow contract**:

- every declared entity must reconcile structurally;
- every source dependency and scope root must be accounted for;
- the decomposition must explicitly self-audit every surface/node/state/interaction;
- a fresh independent reviewer must audit every decomposition entity against source and independently account for observed surfaces;
- review artifacts are cryptographically bound to the exact request and decomposition they reviewed;
- every requested correction must receive an explicit source-backed disposition;
- no unresolved source uncertainty may remain.

No schema can mathematically prove that an arbitrary visual/source tool hid nothing from both independent inspectors. Never describe certification as stronger than the available source and inspection tools justify.

## Input

Treat `$ARGUMENTS` as the original design request verbatim. It may be a Claude Design implementation prompt, local path, URL, attachment reference, or mixture.

If it contains `Implement:`, interpret that as the scope to decompose, not permission to implement.

Default final output: `${CLAUDE_PROJECT_DIR}/ui-decomposition.md`.

If the user explicitly requests another Markdown output path, honor it.

## Fresh-context rule

Every decomposition, structural repair, correction, and adversarial review must use a **new non-fork** `Agent` invocation. Never resume a previous subagent and never provide parent-conversation conclusions.

The delegation prompt must contain only the minimum artifact paths and contract files described below. Claude Code may still inject its standard non-fork subagent context (for example project `CLAUDE.md`); do not add conversation summaries or conclusions. Subagents must inspect the actual source themselves.

Do not set this coordinator skill to `context: fork`; the main session must coordinate several sequential independent subagents.

## Phase 0 — Initialize immutable request state

1. Create a unique working directory:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/init_run.py "${CLAUDE_PROJECT_DIR}"
```

Use the printed absolute path as `WORK_DIR`.

1. Set:
   - `REQUEST=${WORK_DIR}/request.txt`
   - `DECOMPOSITION=${WORK_DIR}/ui-decomposition.json`
   - `OUTPUT=<explicit user path or ${CLAUDE_PROJECT_DIR}/ui-decomposition.md>`
2. Write `$ARGUMENTS` **verbatim** to `REQUEST`. Do not normalize, summarize, or rewrite it.

Never mutate `REQUEST` after this point.

## Phase 1 — Fresh complete decomposition

Spawn one new `general-purpose` subagent.

Give it only:

- absolute `REQUEST` path;
- absolute `DECOMPOSITION` output path;
- `${CLAUDE_SKILL_DIR}/references/decomposition-agent.md`;
- `${CLAUDE_SKILL_DIR}/schemas/ui-decomposition.schema.json`.

Require it to inspect the actual source and write the JSON directly to `DECOMPOSITION`.

### 1A — Structural validation

Run without certification first:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py decomposition "$DECOMPOSITION" --request "$REQUEST"
```

If schema/graph validation fails:

1. Save the exact validator diagnostics to `${WORK_DIR}/repair-errors-<N>.txt`.
2. Spawn a **fresh** repair subagent with only:
   - `REQUEST`;
   - current `DECOMPOSITION`;
   - the repair-errors file;
   - `${CLAUDE_SKILL_DIR}/references/repair-agent.md`;
   - decomposition schema;
   - `DECOMPOSITION` as output.
3. Re-run structural validation.

Allow at most **2** structural repair attempts. If still invalid, stop with `STRUCTURAL_VALIDATION_FAILED`. Preserve all artifacts and report the validator errors. Do not begin adversarial review.

### 1B — Source-certification validation

After structural validation passes, run:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py decomposition "$DECOMPOSITION" --certify --request "$REQUEST"
```

At this point a failure means known source uncertainty remains: unresolved items, uninspected source, or unknown interaction outcomes.

Do **not** repair these by guesswork. Stop with `SOURCE_UNRESOLVED`, preserve the artifact, and report the unresolved blocker(s). Do not begin adversarial review.

## Phase 2 — Adversarial completeness loop

Run at most **3** adversarial review passes. Each review is a brand-new agent.

Use this control flow exactly:

```text
certified = false

for reviewPass in 1..3:
    review = fresh_adversarial_review(current_decomposition)
    validate_review_against_exact_artifacts(review)

    if review.changeRequested == false:
        certified = true
        passingReview = review
        break

    if reviewPass == 3:
        stop REVIEW_LIMIT_REACHED

    correct_with_fresh_agent(review)
    validate_correction_and_decomposition()
```

A maximum pass count and `changeRequested` both constrain continuation. Never use an `OR` loop condition that can exceed three reviews.

### 2A — Fresh adversarial review

For pass `N`, set `REVIEW=${WORK_DIR}/review-N.json`.

Spawn a new `general-purpose` subagent. Give it only:

- `REQUEST`;
- current `DECOMPOSITION`;
- review pass number `N`;
- `REVIEW` output path;
- `${CLAUDE_SKILL_DIR}/references/adversarial-review-agent.md`;
- `${CLAUDE_SKILL_DIR}/schemas/adversarial-review.schema.json`.

Require it to:

1. independently inspect source and privately inventory the UI **before semantically reading the decomposition**;
2. audit every decomposition surface/node/state/interaction;
3. compute SHA-256 for the exact request and decomposition bytes reviewed;
4. write only schema-valid review JSON directly to `REVIEW`.

Validate the review against the exact artifacts:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py review "$REVIEW" \
  --pass-number N \
  --decomposition "$DECOMPOSITION" \
  --request "$REQUEST"
```

The validator rejects stale/wrong-artifact reviews, incomplete per-surface audit ledgers, bad finding references, and inconsistent pass/fail outcomes.

If the review artifact itself is invalid, spawn **one** fresh replacement reviewer for the same pass. If the replacement is also invalid, stop with `REVIEW_VALIDATION_FAILED`. Do not count the invalid artifact as a completed adversarial pass.

### 2B — Fresh correction

If a validated review has `changeRequested: true` and `N < 3`:

1. Snapshot the reviewed decomposition:

```bash
cp "$DECOMPOSITION" "${WORK_DIR}/decomposition-before-review-N.json"
```

Set:

- `BEFORE=${WORK_DIR}/decomposition-before-review-N.json`
- `CORRECTION=${WORK_DIR}/correction-N.json`

1. Spawn a **fresh** correction subagent with only:
   - `REQUEST`;
   - `BEFORE`;
   - `REVIEW`;
   - corrected output path `DECOMPOSITION`;
   - correction report output path `CORRECTION`;
   - `${CLAUDE_SKILL_DIR}/references/correction-agent.md`;
   - decomposition schema;
   - `${CLAUDE_SKILL_DIR}/schemas/correction-report.schema.json`.

The correction agent must source-check every finding. It must explicitly mark every finding `applied` or `rejected-source-contradicts` in the correction report.

1. Validate the correction transaction:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py correction "$CORRECTION" \
  --review "$REVIEW" \
  --before "$BEFORE" \
  --after "$DECOMPOSITION"
```

This binds the correction to the exact reviewed base, requires a disposition for every finding, validates the resulting decomposition, and requires it to remain certifiable.

If correction validation fails, restore `BEFORE` to `DECOMPOSITION` and allow **one** fresh correction retry. If it still fails, stop with `CORRECTION_VALIDATION_FAILED`.

Then continue to the next fresh adversarial review. A reviewer rejection by a correction agent is **not** acceptance; the next independent reviewer adjudicates it.

### 2C — Review limit

If pass 3 returns a valid review with `changeRequested: true`, do not apply another correction in this run and do not claim completion.

Stop with `REVIEW_LIMIT_REACHED`. Preserve `DECOMPOSITION`, all reviews, snapshots, and correction reports so remaining findings are inspectable.

## Phase 3 — Final certification and Markdown

Only after a validated adversarial review returns `changeRequested: false`:

1. Re-run decomposition certification:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py decomposition "$DECOMPOSITION" --certify --request "$REQUEST"
```

1. Re-run the passing review validation against the exact current artifacts:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py review "$PASSING_REVIEW" \
  --pass-number <passing pass> \
  --decomposition "$DECOMPOSITION" \
  --request "$REQUEST"
```

1. Generate the Markdown from the certified JSON and passing review:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/render.py "$DECOMPOSITION" "$OUTPUT" \
  --review "$PASSING_REVIEW"
```

The renderer must not be used to create the final `OUTPUT` before both validations pass.

## Final response

Keep the user-facing response short. Report:

- final Markdown path;
- working-state path;
- adversarial passes used;
- counts of surfaces, component instances, states, interactions, and unresolved items;
- certification status.

On failure, never say “complete.” Report the exact stop status and the artifact containing the blocker/finding.

## Decomposition invariants

The decomposition is implementation-neutral: it answers **what exists, where it belongs, and how it behaves**.

Required principles:

- Every visible or interactive occurrence belongs to exactly one intentional location in a surface tree.
- Shared UI must still have an occurrence on every surface where it appears.
- Every surface has exactly one root node and exactly one default surface state.
- Every non-atomic node has children; every atomic node has none.
- Compound controls with visibly meaningful subparts must not hide those subparts merely because the source uses one DOM element.
- Every interaction that opens/navigates to UI references a documented target surface.
- Every overlay opened from a surface is parented to that source surface.
- Every entity has reproducible evidence.
- Scope roots/exclusions are explicit.
- Coverage ledgers must reconcile exactly with the artifact.
- Certification requires zero unresolved items, zero unknown interaction results, and zero uninspected required source files.

## Resources

- Decomposition worker: [references/decomposition-agent.md](references/decomposition-agent.md)
- Structural repair worker: [references/repair-agent.md](references/repair-agent.md)
- Adversarial reviewer: [references/adversarial-review-agent.md](references/adversarial-review-agent.md)
- Correction worker: [references/correction-agent.md](references/correction-agent.md)
- Decomposition schema: [schemas/ui-decomposition.schema.json](schemas/ui-decomposition.schema.json)
- Review schema: [schemas/adversarial-review.schema.json](schemas/adversarial-review.schema.json)
- Correction schema: [schemas/correction-report.schema.json](schemas/correction-report.schema.json)
