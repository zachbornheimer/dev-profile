# Problem-Solving Standards

When you encounter a bug, performance issue, or unexpected behavior, do NOT jump to a fix. Follow this escalation:

## Step 0: The deliverable is the goal, not an attempt

A request is for an **outcome**, not "a try at it." Proving that one approach cannot reach the outcome does not discharge the request — it **obligates you to find the approach that does, in this change.** "Documented for later," "needs a future rewrite," "out of scope for now," or a fresh ADR that _shelves_ the goal are all **deferral, and deferral is forbidden unless the user explicitly chooses it.** (An ADR records a decision you made and shipped — not a goal you punted. Writing one to avoid the work is the tell.)

**When an approach is blocked, change the _layer_ you act on — never abandon the outcome.** The constraint almost always lives in one layer while the goal can be met in another. Ask: _which layer is the cost/risk actually in?_ — then act there.

> **Canonical example (real, do not repeat the mistake).** Goal: "make big-file chunking fast." Approach A parallelized FastCDC **boundary-finding** — which breaks content-addressed dedup on low-entropy files (VM disks, sparse images), because each boundary depends on the offset since the chunk start, so a mid-stream worker is phase-shifted with no natural boundary to re-align on. **WRONG response:** prove it unsafe, write "needs a new anchor-independent chunker someday," move on. That abandons the goal the user explicitly asked for. **RIGHT response:** ask _where the time actually goes_ — boundary detection is a cheap single pass; the CPU cost is the **per-chunk hash + encrypt + pack.** Keep boundary detection sequential (boundaries stay byte-identical → dedup intact) and **parallelize the per-chunk work.** Goal met now; sacred invariant preserved. The discipline: shift the layer you optimize, don't drop the outcome.

**"Slow but correct" is the floor, never the finish line, when the ask was speed.** Correctness is non-negotiable _and_ so is the asked-for outcome. Do not trade the outcome for the invariant — find the design where you keep both. If you genuinely cannot (rare), that is a real blocker to raise with evidence and options, not a silent downgrade to "documented."

## Step 1: Identify the symptom

State what's broken in one sentence from the user's perspective. Not the cause.

## Step 2: Find the pattern

If you've fixed the "same kind of thing" more than once, you're patching symptoms. Stop. Name the pattern. A pattern is a structural observation about the code, not a description of the symptom.

## Step 3: Question the assumptions

For each instance of the pattern, walk the Socratic chain:

1. **Why was it done this way?** Every choice had a reason. Name the original need it was serving.

2. **Is the need real?** Sometimes yes, sometimes it was assumed. Challenge it.

3. **Does the solution match the need?** Often the solution overshoots — bulk-loading data when point queries suffice, holding everything in memory when a database index exists, blocking on a complete picture when incremental processing works.

4. **What assumption was wrong?** Name it explicitly. Wrong assumptions about scale, ordering, completeness, or timing are the most common.

5. **What interface makes the wrong assumption impossible to express?** The API should make the right path the only path.

## Step 4: Design the replacement

Removing the bad API is half the job. Now design what goes in its place:

1. **What does the caller actually need?** Express it as inputs → outputs. Derive the interface from the caller's contract, not from the existing implementation.

2. **What's the right result type?** Too little forces extra round-trips. Too much creates a god object. Return exactly what the next stage in the pipeline needs.

3. **Does this compose?** Most systems are pipelines. Each stage's output is the next stage's input. Verify the new interface fits the chain — no missing data, no unused data.

4. **Can the implementation satisfy the contract without the bad pattern?** If it can't, the interface is still wrong.

## Step 5: Generate three alternative approaches

Before committing to a solution, generate at least three viable approaches with different tradeoffs. For each, state:

- The approach in one sentence
- The tradeoff (what you gain, what you pay)
- When it's the best choice

This prevents anchoring on the first idea. Often a hybrid of two approaches is better than any individual one. Evaluate them honestly — the "obvious" fix isn't always right.

## Step 6: If the fix is a design change, plan it

If the appropriate fix is a new interface, pattern, or multi-file refactor — don't start coding. Write a plan:

1. **Name the design pattern.** If you can't name it, you don't understand it yet.

2. **Define the new interfaces.** Type signatures before implementation. These are the contract. Review them: does any method invite the bad pattern back?

3. **List every caller that changes.** Group them: trivial swaps vs. callers that assumed bulk access and need rethinking.

4. **Order the migration.** Add new interface alongside old. Migrate callers one by one. Delete old API last. Each step compiles and passes tests.

5. **Verify the design would pass review.** Would a senior engineer at Apple or Google look at the new interfaces and say "of course"? If the design needs explanation, it's not clean enough.

## Anti-patterns

- **Whack-a-mole:** Fixing each instance without naming the pattern.
- **Optimization before design:** Making a bad algorithm faster instead of choosing the right one.
- **Adding comments or logging as fixes:** If the code silently fails, the fix is failing loudly by design.
- **Treating scale as an edge case:** "Works for small datasets" means it doesn't work.
- **Replacing one eager load with another:** Moving a blocking preload to a background goroutine still loads everything — it just blocks later.
- **Removing without replacing:** Tearing out a bad API without designing what the caller uses instead leaves the caller worse off.
- **Shelving the goal:** Proving one approach can't reach the outcome and writing a "future work" note instead of finding the approach that reaches it now. The request was the outcome.
- **Trading the outcome for the invariant:** Accepting "slow but correct" (or "correct but ugly," etc.) when the ask was speed (or polish). The right design keeps the invariant _and_ delivers the asked-for outcome; settling for one is the failure.
- **Optimizing the layer that carries the constraint:** Speeding up the one stage that must stay sequential/safe, instead of moving the work to the layer that's free to change.
- **Acting on a guessed cause:** Taking a corrective — especially a destructive — action (kill, restart, delete, VACUUM, revert) on a _hypothesis_ you haven't proven. Prove the cause first with a direct observation (the actual query plan, a stack `sample`, the real row/data, the log line). A plausible story is not a diagnosis. Every unproven action you take on a live system can make it worse and erodes trust faster than the original bug.
- **Mistaking slow for stuck:** Concluding a process is hung and killing it when it is making slow progress. _Measure before you intervene:_ is CPU-time accumulating, is the WAL/file growing, is a row count or read offset advancing? A big DB / large scan / index build is legitimately slow (minutes), not broken. On a system that protects data, the bias is **wait-and-measure**, not kill-and-retry — killing progressing work and restarting often resets the very progress you were waiting on and compounds the outage.
- **Thrash:** Two or more invasive actions in a row that each chase a new guess (kill the daemon → VACUUM → kill maintain → revert …). If your last action made things worse or revealed your model was wrong, STOP acting, go back to _observe and prove_, and surface the situation honestly before touching anything else. Forward motion on a wrong model is negative progress.

## When you're recovering an incident you caused

If your own change/action broke a running system, the order is: **stabilize → diagnose with proof → one reversible step at a time → verify each step held before the next.** Do not pile fixes. Do not take a destructive step whose blast radius you can't undo. If recovery genuinely needs a user-only action (a credential prompt, a permission), surface it precisely and _wait_ — flailing in the meantime usually deepens the hole.
