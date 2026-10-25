---
name: debug-protocol
description: Load when investigating bugs, failures, or unexpected behavior. The escalation from symptom to structural fix — and the specific traps Claude walks into by default.
---

# Debug Protocol

Do NOT jump to a fix. The protocol is symptom → pattern → assumptions → interface
replacement → three alternatives → plan. Skipping steps produces whack-a-mole.

## The escalation

**Step 0 — The goal is the outcome, not an attempt.**
Proving one approach fails does NOT discharge the request. It obligates you to find
the approach that succeeds — in this change. Deferral is only legal when the user
chooses it explicitly.

> Key move: when blocked, change the _layer_ you act on — the constraint almost
> always lives in one layer while the goal can be met in another.

**Step 1 — Symptom in one sentence from the user's perspective.** Not the cause.

**Step 2 — Name the pattern.** Structural observation, not a description of the
symptom. If you've patched the same class of thing twice, stop and name it.

**Step 3 — Socratic assumptions (for each pattern instance):**

1. Why was it done this way? (name the original need)
2. Is the need real? Challenge it.
3. Does the solution match the need? (bulk load when point queries suffice → no)
4. What assumption was wrong? (name it: scale / ordering / completeness / timing)
5. What interface makes the wrong assumption impossible to express?

**Step 4 — Design the replacement.** Caller's contract first (inputs → outputs);
right result type; composes in the pipeline; implementation satisfies without the
bad pattern.

**Step 5 — Three alternative approaches.** One sentence each + tradeoff + when it's
best. Prevents anchoring on the first idea.

**Step 6 — If structural: plan before coding.** Name the pattern, define type
signatures, list every caller, order the migration (new alongside old → migrate →
delete old).

## Gotchas — the traps Claude walks into

**Whack-a-mole.** Fixing each instance without naming the pattern. Fix the next
instance the same way and you are still whack-a-mole.

**Shelving the goal.** Proving approach A is unsafe and writing "future work" or an
ADR instead of finding approach B. The request was the outcome.

**Trading the outcome for the invariant.** Accepting "slow but correct" when the
ask was speed. The right design keeps both. Settling for one is the failure.

**Optimizing the constrained layer.** Speeding up the stage that _must_ stay
sequential instead of moving the work to the layer that is free to change.

**Acting on a guessed cause.** Taking a corrective (kill, restart, delete, VACUUM,
revert) on a hypothesis you haven't proven. Prove the cause first: actual query
plan, stack sample, the real row, the log line. A plausible story is not a
diagnosis.

**Mistaking slow for stuck.** Concluding a process is hung when it is making slow
progress. Measure before intervening: is CPU accumulating, is the WAL growing, is
a row count advancing? A big scan is legitimately slow, not broken. Bias is
wait-and-measure, not kill-and-retry.

**Thrash.** Two or more invasive actions in a row chasing separate guesses. If the
last action revealed your model was wrong, STOP. Observe and prove before touching
anything else.

## Incident recovery (when you broke it)

Stabilize → diagnose with proof → one reversible step at a time → verify each step
held before the next. Do not pile fixes. Surface any user-only action precisely and
wait — flailing deepens the hole.

---

Full source: `~/.claude/rules/problem-solving.md`
