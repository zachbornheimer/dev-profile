# Autoresearch workflow — fan-out transcript review

Spec extracted from `mastra:thread:13fc33c4-13c7-431b-bdeb-60dbd0f3dd14` (learner ×
GLM 5.3 A/B experiment, 2026-10-23/24) and its final design turn. This is the
mechanized ceiling to pair with the floor prompt in `prompt.md` (same directory).

## Why a workflow, not a better prompt

The experiment's verdict, in the thread's own words: a prompt can set a floor, but it
cannot carry a ceiling. The great root-cause analysis in the master conversation came
from three loop mechanisms no one-shot prompt reproduces:

1. **Specific pushback** ("you didn't identify root causes") — generic "go deeper"
   produces longer checklists, not causal chains.
2. **Evidence contradicting the agent** — the agent's two wrong claims died only when
   it read the actual run manifests; a prompt can request citations, it can't make
   them bite.
3. **Revision with accumulated context** — the best answer was the third pass.

So: mechanize the loop. Deterministic checks where no judgment is needed; parallel
small contexts so monolithic-context failures (summary-trust, truncation blindness,
template flattening) are structurally harder; adversarial revision to mechanize the
pushback. Cost is roughly a wash vs a monolithic run (five 10–50K contexts + parent
+ adversary), wall-clock much faster.

## The DAG

```text
session ref
  .parallel([reconstruct, ground_truth, census, frustration_trace, fix_extraction])
  .then(synthesize)      // parent amalgamator
  .then(attack)          // fresh-context adversary
  .then(revise)          // parent revises once
```

Fixed DAG = Mastra workflow, not an agent factory. Report side of the pipeline; the
landing side is `loop/opportunities/implement_workflow.ts` (contained worktree
code-improver clones), with the report's ranked fix backlog as the intake queue.

## Arm contracts

Every arm: input → one transform or one query → typed output. Fragments carry evidence
(item ids, measurements, file paths); they never write prose for the final report.
All five producers are safe to run alone: if the annotated export is missing, the arm
runs the annotator first (declared input, no cycles).

### 1. `reconstruct` — timeline + functional-completion moment
- **Input:** raw session items (annotated export; annotate if missing).
- **Output:** ordered event list (item id, actor, one-line event), plus the first
  item id where the user's actual request was satisfied and the list of everything
  after it.
- **Evidence rule:** every event line cites an item id. No interpretation of cause —
  causes belong to `synthesize`.

### 2. `ground_truth` — export completeness + true end state (deterministic + small model)
- **Input:** the annotated export AND the raw session log; both required. If the raw
  log is unavailable, the arm's output must say so and mark every end-state claim
  `unverified`.
- **Output:** `export_complete: boolean` (byte/turn-count comparison of export vs raw
  log), the session's true end state (last todo state, last deployed/verified claim,
  final user message), and any discrepancy between export and log.
- **Evidence rule:** never converts an agent's claim into a measurement. This arm
  exists because both A/B glm runs were snapshot-blind and wrong about the end state;
  it cannot be crowded out because it never writes report prose.

### 3. `census` — waste counts, including invisible classes (deterministic + small model)
- **Input:** raw session items.
- **Output:** counts per waste class, adding the classes the current
  `waste-census.py` misses: `unsolicited_execution`, `deliverable_missing` (user
  re-asks for something a prior reply should have contained), `verdict_reversal`
  (two contradictory verdicts on the same target), orphaned-process recovery, and
  intent-level `user_recovery` (corrective user turns that no tool error explains).
  Also reconcile annotator labels (e.g. "denied tool") against the counted classes.
- **Evidence rule:** each counted event cites item ids; each class not present says 0
  explicitly.

### 4. `frustration_trace` — onset and earliest divergence
- **Input:** raw session items, user turns only for onset detection.
- **Output:** frustration onset item id (first corrective/emotional user turn),
  escalation turns, and the earliest divergence item id before onset.
- **Evidence rule:** quotes the user text verbatim, ≤160 chars each. Divergence must
  be an item that exists, not a paraphrase.

### 5. `fix_extraction` — fixes with files and red tests
- **Input:** the other four fragments + raw items they cite.
- **Output:** candidate fixes, each `{claim, root_cause_id, file, red_test}` where
  `red_test` is a check that fails against today's code.
- **Evidence rule:** a fix without a real file path and a real red test is dropped
  here, not by the parent.

### 6. `synthesize` — parent amalgamator
- **Input:** all five fragments PLUS read access to raw items. Must not glue: it
  re-reads the raw items that fragments cite, re-derives the causal chain across
  arm boundaries, and produces the report per the floor prompt's Report shape.
- **Resolution rule (stated in output):** raw items beat summaries, measurements
  beat impressions, the raw log beats the export, `ground_truth` beats every other
  arm on end state.
- **Output:** the draft report, one-line root cause first.

### 7. `attack` — adversarial revision arm (fresh context)
- **Input:** the draft report + raw items + raw log. Never sees the fragments or
  the parent's reasoning.
- **Job:** try to falsify every material claim. Do the cited item ids exist and
  contain the claimed text? Does the stated end state hold against the raw log?
  Which claim would a hostile reader break first? Is the "one-line root cause"
  actually one gap, or six findings wearing a summary sentence?
- **Output:** per-claim verdict (`holds` / `breaks` + the item id that breaks it),
  ranked by damage.

### 8. `revise`
- **Input:** draft + attack verdicts + raw items.
- **Job:** the parent revises once. Claims that broke are corrected or retracted and
  listed in Corrections.

## Deterministic checkers (run on the final report, no model)

1. **Citation checker:** every item id cited in the report exists in the session and
   contains the claimed text. Red test: a report citing item 999 fails; a report
   citing real items passes.
2. **End-state checker:** the report's stated end state equals `ground_truth`'s.
   Red test: a report claiming the export's truncated end state against the raw log
   fails.
3. **Red-test runner:** each fix's stated red test, executed, fails today (or is
   marked `cannot-run` with reason). Red test: a fix whose "failing" test passes is
   dropped.

## File plan (capability-replicas/mastra/src/loop/learning/)

- `autoresearch/workflow.ts` — the DAG above, reading as the flowchart.
- `autoresearch/` one file per arm; sibling `questions/*.yaml` where the arm asks the
  model (match the AgentMux question shape; no prompt text in TypeScript).
- Checkers as plain scripts under `autoresearch/checks/`.
- Composes with existing pieces: `annotate.ts` (annotation), `wastes.ts` /
  `waste_detectors.ts` (census inputs), `session_items.ts` (item source),
  `learn_summary.ts` / `fileSummaryWriter` (report output),
  `opportunities/implement_workflow.ts` (landing side, report backlog as intake).

## Known open items from the source thread

- The gate-fix code-improver run (at-mbj478) is presumed dead — completion gate
  blocks subagent turns with empty `user_request`; must be fixed before any of this
  fans out reliably.
- Item 432-class harness-injected `<critical>` text is annotated `correction: true`,
  poisoning user-recovery counts; the census arm must special-case it.
