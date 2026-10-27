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

## Closure gate — before the first edit on a measured defect

A defect with a number on it (latency, size, memory, failure rate) gets no edit
until all four artifacts exist in writing, in the turn, before the diff:

1. **Floor.** Measure the same operation on a best-known-good platform or
   baseline (another tool, another build, the minimal program that does the
   same work). The floor is the achievable minimum; the gap over it is what you
   are explaining.
2. **Time budget.** Account for the whole gap over the floor, stage by stage,
   with measured numbers. An unexplained remainder means the diagnosis is
   incomplete — keep measuring; do not edit against a partial budget.
3. **Owner config + upstream.** Read the owner library's or tool's public
   config/option surface and docs (grep the nouns of the symptom: component,
   setting, error names), then check its upstream issues and releases. A
   documented option or an already-landed fix beats a patch or a fork.
4. **Incorrectness answer.** Write the causality in one paragraph: "why is this
   wrong at this layer?" — what the owner layer does that it should not, not
   what the symptom looks like.

**A fix that only skips a consequence is re-planned at the owner layer.**
Suppressing, short-circuiting, or exiting before the costly step hides the
defect; if the incorrectness answer names a different layer, the edit belongs
there (a config option, a fix upstream of the skip), not at the symptom.

**Independent check.** Before landing, hand a fresh context (a subagent with no
shared history) only the problem statement and the raw measurements — never the
diff and never your narrative — and ask: "what would make this fix
unnecessary?" An answer that names a cheaper lever you have not ruled out sends
you back to artifact 3. Anything you tell the checker beyond the problem and the
measurements defeats the check.

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
