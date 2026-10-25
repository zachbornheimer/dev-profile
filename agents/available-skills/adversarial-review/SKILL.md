---
name: adversarial-review
description: Run an adversarial review that tries to break the work before it ships — code, a diff, a PR, a file, a design doc, a plan, or an architecture. Use whenever the user asks to adversarially review, red-team, stress-test, "try to break", poke holes in, or find what's wrong with anything, before merging, pushing, or committing to a high-stakes decision — and any time a review felt too agreeable or the work's author is the one reviewing. Runs independent fresh-context adversaries with distinct attack roles — from a quick two-adversary pass on a small diff to the full six-role cast — verifies every finding against evidence, and opens a severity-ranked BLOCK/CONCERNS/CLEAN report in lavish with the Zysys theme. Not Zach's-Bar done-gating (review-bar), not a security-only audit (security-audit), not a PR walk-through (pr-review).
---

# Adversarial review

Attack the work before it ships. Recruit independent, fresh-context adversaries
whose only job is to break it, hold every finding to an evidence bar, then open a
severity-ranked report in lavish. The maker never grades their own work in their
own context — the research on self-review bias says they will be generous exactly
where the work is wrong, so that separation is the whole mechanism.

## Platform terms

- **Parent**: the agent running this skill. Coordinates, adjudicates, owns the
  report. Not read-only — the parent runs reproductions (step 4).
- **Task tool**: the platform's subagent/delegation mechanism.
- **Adversary**: a read-only subagent spawned with exactly one attack role.
- **run_command**: the platform's command-execution tool (for example
  agentmux_run; harnesses that name it differently have an equivalent). Every
  command any agent in this run executes goes through it.

## Cost envelope — pick the profile first

The full pipeline costs real tokens: adversaries, adjudication, report, lavish.
Match spend to the target before spawning anything:

- **quick** — Saboteur + Requirements adversary. Small diffs (under a few
  hundred changed lines), re-checks, low stakes.
- **full** — the artifact's default cast (step 3). Stated maximum: 6 adversaries.
- **Manifest cap**: once the target exceeds a few hundred lines, the manifest
  carries paths and line ranges, not pasted text. Never paste a large diff into
  every work order.
- **No task tool, or every spawn failed**: say the platform cannot run
  independent adversaries and stop. Never substitute in-context self-review —
  that is the failure mode this skill exists to prevent, delivered under its own
  label.

## Workflow

### 1. Resolve the target — and confirm it

- No argument: `git status --porcelain` first. The target is the union of staged
  (`git diff --cached`), unstaged (`git diff`), and untracked files. Brand-new
  files are the most common shape of pre-ship work, and the two diffs alone never
  see them.
- All three empty: `git diff HEAD~1` is a guess. Name it back and get confirmation
  before spawning — a full adversarial round spent on the wrong diff is false
  assurance, worse than no review.
- `--diff <ref>`, `--file <path>`, a bare path, a PR number or URL, or a named
  plan or design doc: gather its content first.
- Git fails (no repo, no `HEAD~1`): treat as no target — ask for an explicit
  `--file` or `--diff`.
- No target at all: stop and report "Nothing to review." Do not invent scope.
- Before spawning, name the resolved target and its diffstat or file list back,
  against the stated outcome.

### 2. State the outcome, build the manifest

- **The intended outcome is quoted verbatim from the user's request or ticket.
  The parent never paraphrases it.** A maker who quietly narrowed scope must not
  also write the criterion its own work is judged against.
- The manifest — every adversary's entire input, and nothing else from the
  parent's conversation or reasoning:
  - the target: file paths plus line ranges, or document text within the cap
  - the verbatim outcome, and hard constraints (contracts, budgets, deadlines)
  - the project conventions that define "wrong" (test practices, standards, repo
    rules), where they exist
- If the parent authored the work, the fresh adjudicator (step 4) validates the
  manifest before adversaries spawn.

### 3. Recruit the adversaries

| Role                   | Attacks                                                             | Artifact types            |
| ---------------------- | ------------------------------------------------------------------- | ------------------------- |
| Saboteur               | worst input, failure paths, double-execution, races, resource leaks | code, diffs               |
| Security auditor       | trust boundaries, injection, authz, secrets                         | code, config              |
| New maintainer         | six-months-later comprehension, names, coupling                     | code, docs                |
| Operator               | the 3 a.m. failure: recovery, observability, cost, blast radius     | code, infra, plans        |
| Requirements adversary | does the work satisfy the stated outcome; spec violations           | anything                  |
| Pre-mortem historian   | "it is six months later and this failed — write why"                | plans, designs, decisions |

Casts: **quick** = Saboteur + Requirements adversary. **Code or diff** =
Saboteur, Security auditor, New maintainer, Requirements adversary — add
Operator when the change touches runtime behavior. **Plan, design doc, or
decision** = Pre-mortem historian, Requirements adversary, Operator, New
maintainer.

- Spawn every adversary in ONE parallel batch. Serializing lets later
  adversaries inherit earlier findings; anchoring destroys independence.
- Fresh context, read-only tools, and each adversary spawned from the template in
  [references/attack-roles.md](references/attack-roles.md). Pin an explicit model
  in every spawn — never let an adversary inherit the parent's tier — and prefer a
  family different from the maker's: same-family models share blind spots and
  agree confidently in the same places.
- Each adversary writes its findings block to `<run-dir>/findings/<role>.md` and
  returns it in its reply. The block format is defined once, in the template.

### 4. Reconcile, then adjudicate

**Step 0 — reconcile**: exactly one role-tagged findings block per spawned
adversary. Missing, malformed, or wrong-role block → one respawn of that role; if
it fails again, record the gap in the report's scope line. A run that lost
adversaries is a partial run and says so.

Severity anchors — the only copy; the parent pastes them into each work order:

- **blocker** — data loss, security breach, outage, or the stated outcome is not met.
- **major** — likely failure in real runs; real operational or maintainability harm.
- **minor** — should fix; no urgency.
- **nit** — polish.

Then:

1. **Dedupe by root cause**, not by wording. Record every role that caught it.
2. **Verify every citation**: re-open the cited file:line or passage. A finding
   that does not survive re-reading is discarded, not downgraded — listed in the
   report with the reason.
3. **Reproduce behavior claims**: a finding that claims the work crashes,
   returns the wrong thing, or grants access gets the smallest reproduction, run
   by the parent — adversaries are read-only, the parent is not. No repro →
   fragile assumptions. Reading alone produces confident false positives on
   behavior claims; the libfuse campaign in
   [references/methodology.md](references/methodology.md) is the evidence.
4. **Promotion**: a root cause caught by two or more adversaries promotes one
   level, from the higher base severity, **capped at major** — corroborated
   findings never manufacture blockers. The fragile-assumption rule outranks
   promotion: a corroborated suspicion stays a fragile assumption, with a
   corroboration note.
5. **Verdict**: BLOCK (any blocker) / CONCERNS (no blockers, one or more majors) /
   CLEAN (minors and nits only).

If the parent authored the work, a fresh adjudicator runs this whole step —
brief and template in [references/attack-roles.md](references/attack-roles.md).
It receives the raw blocks, the manifest, and a snapshot of the reviewed revision;
it returns the adjudicated set and verdict; the parent writes the report from it.

### 5. Bound the rounds

A round is spawn → adjudicate → report. Fixes happen outside this skill, between
rounds. Default: one round. A second round re-attacks only the surviving
blockers and majors, on the fixed revision. Never a third.

### 6. Write the run directory

Every run gets its own directory outside the target — default
`~/adversarial-review/<repo>/run-<N>`, next unused N. A throwaway run may use a
/tmp path, stated in the report. Never write the report into the target's tree.
It holds:

- `report.md` and the lavish HTML with its copied design-system CSS
- `findings/` — the adversaries' raw blocks, and `adjudication.md` when one ran
- a snapshot of the reviewed revision, so citations stay checkable after fixes

### 7. Write report.md

ALWAYS this exact template:

```markdown
# Adversarial review: <target in one line>

**Verdict:** BLOCK | CONCERNS | CLEAN — <one honest sentence>

**Scope:** <files/lines or doc sections> · <artifact type> · <adversary roles,
with any respawn or reconciliation gaps> · <rounds>

Per finding, in every severity section below:

### [<severity>] <roles> (promoted: yes|no) — <file:line or passage> — <issue>

Evidence, impact, smallest fix.

## Blockers

## Majors

## Minors and nits

## Fragile assumptions

<unproven suspicions, labeled as such>

## Discarded findings

<citation> — <reason> (when any)

## Summary

2–3 sentences: the overall risk profile and the single most important fix.
```

Do not soften the verdict. "Essentially clean" is not CLEAN.

### 8. Open the report in lavish (Zysys Admin)

The lavish artifact is the review's face: the user annotates it in the browser
and sends feedback back.

1. Open every matching playbook before writing any HTML:
   `npx -y lavish-axi playbook explanation` and `npx -y lavish-axi playbook table`
   (add `code` when evidence needs source snippets).
2. Read `~/.agents/lavish-design-system/AGENT.md` and `README.md`, and follow them:
   - copy `colors_and_type.css`, `tokens.css`, and `components.css` from that
     directory next to the HTML; link them with relative paths, never a leading `/`
   - use the CSS variables, never hex values; one filled `btn primary` per view
   - reuse component markup from `components/<Name>/preview.html`
     (Card, DataTable, HealthDot, DiffBlock are the usual set)
   - copy rules follow `guidelines/voice.md`: sentence case, concrete numbers,
     meta lines joined with "·", buttons are verbs
   - Zysys Admin is the default, subject to the precedence rules in
     `~/.agents/lavish-design-system/AGENT.md`: a look named in this turn, or a
     mocked app's own design system, wins.
3. The page must carry, in order: a verdict banner (HealthDot color: green CLEAN,
   amber CONCERNS, red BLOCK), the scope meta line, findings ordered by severity
   with role tags, evidence, impact, and fix for each, fragile assumptions marked
   unproven, then the summary.
4. Open it: `npx -y lavish-axi <html-file>`. Say the artifact is open for
   annotation. If lavish-axi refuses to reopen a session the user ended, re-run
   with `--reopen`. If the user wants the feedback loop, follow the lavish skill:
   `npx -y lavish-axi poll <html-file>` or `npx -y lavish-axi reply`.

## Anti-patterns

| Anti-pattern                                       | Why it's wrong                                                                                                                               |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| "LGTM, nothing found"                              | Nobody looked hard enough. The adversary's own second look (work-order template) is the retry; it ends in a fragile assumption, not silence. |
| Reviewing in the maker's context                   | The reviewer inherits the assumptions that produced the bug; the second pass restates the first opinion.                                     |
| Paraphrasing the outcome                           | The maker must not write the criterion its own work is judged against; quote the request verbatim.                                           |
| Silent adversary loss                              | A missing or malformed block is a partial run; reconcile, respawn once, and record the gap — never report a full cast that did not run.      |
| Serial adversaries                                 | Later adversaries anchor on earlier findings; independence is the method.                                                                    |
| Hedged findings                                    | "This might possibly be a concern" is unusable. State it or drop it.                                                                         |
| Restating the diff                                 | "This adds a handler" is not a finding. Say what is wrong with the handler.                                                                  |
| Unverified citations, unreproduced behavior claims | Re-read every citation; reproduce behavior claims or demote them. Reading alone endorses false positives.                                    |
| Unbounded spend                                    | Full cast on a tiny diff, or a pasted 5,000-line manifest in every order: pick the profile, cap the manifest.                                |

## References

- [references/attack-roles.md](references/attack-roles.md) — role briefs, the
  adversary work-order template, and the adjudicator brief. Read before spawning.
- [references/methodology.md](references/methodology.md) — why each rule exists,
  with sources. Read when adapting or extending the method.
