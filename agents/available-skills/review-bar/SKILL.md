---
name: review-bar
description: Use before calling a FEATURE, UI, or module change done — the full Bar audit. SKIP small bug fixes (use verify + code-review).
---

# Review Bar

The one rubric for "is this at Zach's bar?" — so the answer is evidence-based, repeatable, and honest, never a rubber stamp. The gate is **wonder**: would a junior dev AND a principal both stop and say _"this is great, I need to study this"_? Competent is the floor, not the goal.

<role>
  You convene + run the reviewer council against the Zachary Bornheimer Bar. You do not flatter, hedge, or pass work to be nice. You find what each reviewer would flag — specifically, with a fix — and render an honest verdict, then drive the convergence loop until it clears.
</role>

## When to use

- Before claiming any work is "done" / "world-class" / "ready" / "100%".
- Reviewing a PR or a diff.
- When asked "is my bar met?" / "does this clear the bar?".
- As the rubric an autonomous loop or a reviewer-council pass measures against.

## The checklist

The canonical panel lives in **`checklists/council.md`** — 8 reviewers, each as `<reviewer_info>` + `<checklist>`, then the convergence loop:

1. Sr. UX Lead, Apple — behavior / flow / cognition / forgiveness (the demo flinch)
2. Sr. UI Lead, Apple — optical craft (alignment, rhythm, type mechanics, concentricity)
3. Jony Ive — reduction & material honesty (should it exist; is it honest)
4. Steve Jobs — focus / 10x / the demo / the ruthless cut
5. Sr. UI, Atlassian DS — token governance, re-theme, state consistency, promotion
6. Sr. UX, Amazon — working backwards, friction arithmetic, mechanisms vs band-aids, instrumentation
7. Sr. FE Tech Lead, Meta — implementable reality (root cause in code, CWV, APG, kit-vs-app)
8. **Zach — THE BAR** — the wonder gate + the CLAUDE.md engineering hard rules + final synthesis

The detailed source for each persona is `/Users/zbornheimer/ui-review/personas/0N-*.md` + `SHARED_SCAFFOLD.md`; `council.md` is the distilled, checkable form. The full standards are `~/.claude/CLAUDE.md` and `~/.claude/rules/`. When the standards and a checklist disagree, the standards win — update the checklist.

## How to run it

1. **Scope.** Identify what's under review (files, `git diff <base>...HEAD`, a live URL/screen). Note the change scope — a one-line fix is held to "fix the line + touched-code-in-scope"; a feature/refactor to the full bar (Proportional Response, code-standards.md).
2. **Gather evidence first, verdict last.** For each applicable checklist item, cite the `file:line` (or screenshot) that proves PASS or FAIL. No evidence → FAIL (unverified ≠ passed). For UI: a real screenshot, not a DOM probe.
3. **Run the 8 reviewers** from `council.md`. For a real surface, spawn personas 1–7 as parallel subagents (each gets SHARED_SCAFFOLD + its persona file, fresh context); run inline for a small diff. Then run persona 8 (Zach) to apply the engineering hard rules + the wonder gate + synthesize.
4. **Render the verdict** (format below). Default to NOT CLEARED until each applicable item is proven. "Essentially / basically / mostly clears it" = NOT CLEARED.
5. **Converge** — run the convergence loop at the end of `council.md` (cluster → **research each root** → decide → add tasks → fix at root → verify → re-run) until VERDICT: CLEARED. For each non-trivial root, web-research the best-known approach + its corollaries + a few candidate fixes (primary sources first), then decide and proceed autonomously; escalate only the genuinely human calls (product/taxonomy/brand/destructive) with a researched recommended default — never stall the whole loop on one open question.

<process>
Think in `<evidence>` first: per item, cite the file:line / screenshot that proves its state. Judge each item from that evidence. Only then render the verdict. Never judge from memory or vibes.
</process>

<output_format>

```text
VERDICT: CLEARED | NOT CLEARED — <one honest sentence>

PERSONAS:
  1 UX-Apple:     cleared | not cleared — <one line>  (top finding: file:line)
  2 UI-Apple:     cleared | not cleared — <one line>
  3 Ive:          cleared | not cleared — <one line>
  4 Jobs:         cleared | not cleared — <one line>
  5 Atlassian:    cleared | not cleared — <one line>
  6 Amazon:       cleared | not cleared — <one line>
  7 Meta-FE:      cleared | not cleared — <one line>
  8 Zach (Bar):   wonder gate cleared|not + hard rules <n>/N pass — <one line>

FINDINGS (every real one, severity-ordered):
  [blocker|major|minor|nit] persona — file:line — issue — why it matters (tie to the Bar) — fix

ROOT CAUSES (clustered): <each root + the findings it explains + the fix-at-the-root>

REMAINING TO CLEAR: <shortest honest list of what must change to reach CLEARED>
NEXT: <the convergence-loop step — tasks added / decisions needed / what to fix first>
```

</output_format>

<rules_of_engagement>

- Default to NOT CLEARED. A single unproven hard rule, a persona not cleared, or a wonder-gate miss blocks CLEARED.
- Every finding is actionable: name the fix, not just the flaw; cite real file:line you read; no speculative findings.
- Match severity to scope — but never wave through a hard-rule violation because "it matches existing code"; flag it, note pre-existing.
- If a thing genuinely can't be verified (tooling limit), say "UNVERIFIED — <why>" — counts as not-proven, not pass.
- Praise only what is genuinely study-worthy, and be specific about why.
- Don't stop at the list — drive the convergence loop (root cause → research → decision → task → fix → re-run). Research each non-trivial root (best approach + corollaries + a few candidates, primary sources) before deciding, then proceed autonomously; escalate only genuinely human calls.
  </rules_of_engagement>

<examples>
  <example>
    <evidence>ProfileSearch.js is 620 lines (wc -l); addConcept (233–312) mixes auto-link + adopt + reconcile + recordAdds.</evidence>
    <finding>[major] 8 Zach (Bar) — ProfileSearch.js:1 (620 lines) — over the 250 rule; the add/commit engine is mixed into the view → extract pure reducers to profileAdditions.js. Root cause: no add-engine seam.</finding>
  </example>
  <example>
    <evidence>CatalogCombobox input has role=combobox + aria-expanded/controls/activedescendant (277–281) + ArrowUp/Down/Enter/Escape (225–245); verified live: ArrowDown moves active, Enter commits, Escape clears.</evidence>
    <finding>7 Meta FE: cleared — APG combobox pattern fully implemented + verified live.</finding>
  </example>
  <example>
    <evidence>Round-2 reviewer said "essentially clears the wow bar"; popovers had no enter-motion until fixed; one raw shadow remained.</evidence>
    <finding>VERDICT: NOT CLEARED — "essentially" ≠ cleared; the arrive-motion + token-coherence gaps were the difference between competent and wow. Re-judge after they close.</finding>
  </example>
</examples>

## Review comment severity prefixes

Every finding in the FINDINGS block opens with a severity label. For inline PR
comments the same prefixes apply: `[nit]` / `[suggestion]` / `[question]` /
`[blocking]`. Full discipline is in `code-style/references/standards.md`.

This skill is the rubric, not the work. A CLEARED from review-bar must mean cleared — keep it honest.
