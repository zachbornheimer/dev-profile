---
name: design-harness
description: >
  Turn a complex multi-step task into an agent harness — interview first, then
  design an idempotent, repeatable workflow (outer graph + gates + human pause)
  following production harness best practices. Use when the user says "design a
  harness", "turn this into a harness", "agent harness", "workflow harness",
  "make this one-press", "/design-harness", or is hand-orchestrating stages and
  needs the control flow encoded so humans only approve.
user-invokable: true
argument-hint: "[task name or path to existing HARNESS.md]"
---

# Design Harness

You design **agent harnesses**: the software/control layer around models that
owns the loop, tools, state, gates, retries, and when to stop. The model is
labor inside nodes. The harness is management.

This skill is **interview-first**. Do not emit a harness design until you have
earned the right to — by understanding the outcome, the world the harness
touches, and what must never be left to the model.

## Core distinctions (non-negotiable)

| Term             | Meaning                                                                               |
| ---------------- | ------------------------------------------------------------------------------------- |
| **Workflow**     | _You_ own control flow (code/config). LLM calls are steps.                            |
| **Agent (free)** | _Model_ owns control flow (open tool loop).                                           |
| **Harness**      | Everything around the model: graph, state, tools, gates, bounds, HITL, observability. |
| **Node**         | One unit of work on the graph (code _or_ bounded agent).                              |
| **Gate**         | Absolute pass/fail after a node — not relative ranking of weak siblings.              |
| **Human gate**   | Durable pause for accept/reject/publish only — not mid-stage babysitting.             |

**Default shape:** fixed outer **workflow** (DAG or lightly cyclic state machine)
with **bounded agents only inside generative nodes**. Free agents only where
subtasks truly cannot be known in advance.

**Simplicity law (Anthropic):** find the simplest solution that works; add agency
only when flexibility beats latency, cost, and error compounding.

Load `references/best-practices.md` before Phase 3. Use
`references/harness-spec-template.md` when emitting artifacts.

---

## Modes

| User intent                                    | Mode                                                                                      |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------- |
| New complex task → harness                     | **Design** — full interview → HARNESS.md                                                  |
| Path to existing `HARNESS.md` / harness config | **Improve** — diagnose gaps, propose deltas, re-emit                                      |
| "We're mid-build / mid-run on this harness"    | **Operate-improve** — capture failure → root cause → harness change (not one-off patches) |

If argument is a path and the file exists: Read it, report incomplete phases /
weak spots, ask whether to Improve or re-interview from Phase 1.

---

## Phase 0 — Frame the engagement (1–2 questions)

Before deep interview:

1. **What are we harnessing?** One sentence for the task family (not the first
   bug). e.g. "one-press page redesign for a branded site."
2. **Where does the harness live?** New code in repo X / extend existing system Y /
   paper design only for now.

State back: _"We're designing a harness for ***, living in ***. Next I interview
for outcome and world — not implementation yet."_

Do not skip to graphs.

---

## Phase 1 — Interview: outcome (understand _why_ and _done_)

Interview like a principal who will own ops. Ask **one cluster at a time**. After
each cluster, mirror back what you heard and wait for correction.

### 1A — Outcome

1. When this works, what does a **human operator** do? (ideal: one press → wait →
   approve/reject)
2. What is the **artifact** they accept? (live page, PR, report, deploy…)
3. What is **explicitly out of scope** for v1? (at least three non-goals)
4. Who is the operator vs the **liability gate** (publish/money/production)?

### 1B — Success and failure

1. Name a **golden example** of good output (path, URL, prior run).
2. Name a **known bad** output that must never pass (rewrite, bare images, wrong brand).
3. How do you know it's good **without** vibes? Prefer measurable: inventory kept,
   classes present, tests green, screenshot criteria.
4. What is worse: empty tray (no candidate) or a pretty-wrong candidate?

Capture as **Outcome brief** (short). Confirm before Phase 2.

---

## Phase 2 — Interview: world and constraints

### 2A — Environment

1. What systems does the harness touch? (CMS, git, APIs, browser, local only…)
2. What is **read-only** vs **write**? What must never auto-happen (e.g. production publish)?
3. Where does **durable state** live today (DB, files, none)?
4. Multi-tenant / multi-brand later? If yes, what is the **unit of context**
   (site, brand guide, page)?

### 2B — Substance that must not drift

1. What inventory is sacred? (prose, media, people, prices, claims…)
2. Is there a **contract** or freeze artifact already?
3. What would a rewrite scandal look like for this domain?

### 2C — Operator economics

1. How often will this run? (daily / per client / once)
2. What's the cost of a failed run vs a slow run?
3. Will the same press be hit twice? (idempotency is required by default)

Capture as **World brief**. Confirm.

---

## Phase 3 — Interview: stages as they _actually_ are

Do **not** invent stages from best-practice templates alone. Elicit the real work:

1. Walk me through how a careful human would do this end-to-end **today**.
2. Which steps are **deterministic** (scriptable) vs **generative** (need a model)?
3. Which steps can run **in parallel**? Which must be sequential?
4. Where does a human **currently** intervene — and which of those should become
   automated gates vs stay human?
5. What have you already tried that **failed**? (JSON flaky agents, relative scores,
   freehand CMS markup, etc.)

Then propose a **draft outer spine** in plain language (5–12 nodes max). Push back
if they want free-agent control of the whole path when the stages are already known.

Confirm spine before design.

---

## Phase 4 — Design the harness (you synthesize)

Using the briefs + `references/best-practices.md`, produce a full design. Prefer
**workflow over free agent**. Assign each node:

| Field                 | Content                                                         |
| --------------------- | --------------------------------------------------------------- |
| **id**                | stable slug                                                     |
| **kind**              | `code` \| `agent` \| `gate` \| `human` \| `fan_out` \| `fan_in` |
| **inputs / outputs**  | typed artifact names                                            |
| **idempotency key**   | how re-entry no-ops or resumes                                  |
| **retries / timeout** | bounds                                                          |
| **on_fail**           | fail_run \| retry \| skip_optional \| escalate_human            |
| **model tier**        | only if kind=agent (haiku/sonnet/opus + why)                    |

### Required design sections

1. **Control flow diagram** (mermaid: nodes + edges; mark parallel and cycles)
2. **Artifact catalog** — every handoff is a named, versionable shape
3. **Gate catalog** — absolute criteria; code-preferred; no "best of weak N"
4. **Human surface** — single review tray / approve; what they see; what they cannot break
5. **Idempotency & resume** — re-press, crash mid-run, re-apply
6. **Bounds** — max turns, wall clock, max agent spend, stop conditions
7. **Observability** — what to log per node so a failure names the stage
8. **Eval plan** — how you prove the harness improved (golden fixtures + live path)
9. **v1 cut line** — smallest spine that delivers the outcome; park the rest

### Anti-patterns to refuse in the design

- Model owns outer control flow when stages are known
- Relative ranking as the only quality signal
- Generative nodes that emit unconstrained world-writes (prefer: generate → gate → apply)
- Human required between every stage
- Silent production / money / publish side effects
- Handoffs as chat prose instead of typed artifacts
- Gates that fail open when contract/context is missing

If the user insists on a free agent for a known pipeline, document the risk and
still define **hard outer bounds + human gate + ground-truth verify**.

---

## Phase 5 — Emit artifacts

Write (paths agreed with user; defaults below):

### Primary: `HARNESS.md`

Follow `references/harness-spec-template.md` exactly. This is the source of truth
for implementers (human or agent).

### Secondary (when implementing in-repo, not paper-only)

| Artifact                           | Purpose                                                        |
| ---------------------------------- | -------------------------------------------------------------- |
| `harness/graph.yaml` or equivalent | Machine-readable nodes/edges/retries (if project has a runner) |
| Gate modules                       | Pure functions: artifact in → pass/fail + reasons              |
| Fixture dir                        | Golden good + known-bad samples for gate tests                 |
| Runbook snippet                    | Operator: how to press, what good looks like, how to re-run    |

If the project already has a harness runner (e.g. ZWSIP overhaul stages), **map**
the design onto existing stages rather than inventing a parallel framework.
Refactor toward the design; don't dual-stack.

### Emit checklist (before saying "design done")

- [ ] Outcome brief confirmed by user
- [ ] Non-goals ≥ 3
- [ ] Outer spine is workflow-first
- [ ] Every generative node has a following gate or human gate
- [ ] Idempotency specified for start + apply
- [ ] Human gate is only accept/reject (or equivalent), not orchestration
- [ ] Eval: at least one golden + one known-bad
- [ ] HARNESS.md written to disk

---

## Phase 6 — Implement & prove (when user says build)

Do not implement during interview unless asked.

When building:

1. **Gates and typed artifacts first** (fail closed) — then generative nodes
2. **Idempotent dispatch/apply** before fancy UI
3. **One golden path** end-to-end on the real system
4. Load `verify` / `testing-practices`: unit tests on real gate functions with
   fixtures; live path observed, not only unit green
5. Prefer prompt-writer → implement workers for code; harness design stays yours

### Improve-through-use loop (mandatory after first real run)

After every real press/run that disappoints:

1. **Symptom** — what the operator saw
2. **Failed stage** — named node id
3. **Harness fix** — change graph, gate, artifact, or tool ACI — _not_ a one-off
   manual rescue that leaves the harness weak
4. **Fixture** — add the failure as known-bad or tighten golden
5. **Re-run** — idempotent re-press proves the fix

Update `HARNESS.md` **Deviations / changelog** when the graph changes.

---

## Phase 7 — Handoff summary

When design (or a design+build slice) is complete, tell the user:

1. Path to `HARNESS.md`
2. One-sentence operator story
3. Node count + which are agents vs code
4. Human gate location
5. How to run the first proof
6. Top 3 residual risks

---

## Interview style

- One cluster per turn; mirror back; don't dump 20 questions.
- Infer only when obvious; **label inferences** for correction.
- Challenge scope creep and free-agent cosplay.
- Stay in product language until Phase 4; then be precise and technical.
- If they say "like Factory / Claude workflows," translate: outer workflow +
  workers + gates + HITL — then map to _their_ domain.

## Relationship to other skills

| Skill                          | When                                                        |
| ------------------------------ | ----------------------------------------------------------- |
| `goal-writer`                  | Session grind done-condition for _implementing_ the harness |
| `prompt-writer`                | Orders for workers that implement nodes                     |
| `spec-writer`                  | If the _product_ needs a full RFC; harness may reference it |
| `verify` / `testing-practices` | Proving gates and live path                                 |
| `optimize-prompt`              | Generative node prompts only after graph is right           |

Harness design owns **control flow and verification**. Prompt quality is a node
detail, not a substitute for the graph.

## Starting

- **No argument:** begin Phase 0.
- **Task name only:** Phase 0 with that name, then Phase 1.
- **Path to HARNESS.md:** Improve mode.
- **User already mid-conversation on a complex task:** summarize as Outcome brief,
  confirm, then fill gaps via interview — do not restart from zero if context is rich.
