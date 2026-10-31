# Handoff blocks

Load this when compiling an implement / code-edit / long-running order. Include
what the worker needs; do not recopy into every trivial one-shot.

## Code approval brief (implement / code-edit orders)

Point them at skill `code-style` + `references/approval-dossier.md` and require
they load it before editing, or paste:

```text
Write code Zach would approve.

COMPOSITION: Right abstraction from atoms that are well-constructed, performant,
testable, observable, maintainable (incl. AI). Jazz subtraction — every note
earns its place. ≤2 motives. Childlike surface, intricate interior.
Atom stack: values → pure functions → facades → policies → workflows.

TWO BARS: Rigid interior (facades, SRP, no magic, small units, three-way tests)
AND idiot-proof exterior (honest state, great defaults, overridable). Never trade.

TECH: facade every edge; WHAT-not-HOW names; structure limits (~250/50/3/5);
contextual errors; search before create; red→green bugfixes; prove real end-state;
no gate bypass; comments only for must-know; subtract before PR.

Load skill code-style (+ testing-practices if tests/bugs; bar for feature/UI).
Do not Read prompt-writer/SKILL.md or code-construction/SKILL.md by path
unless this spawn is editing those files.
```

## Universal guardrails (any non-trivial handoff)

Two failure modes show up across models under pressure. Include both unless the
order is a one-shot mechanical edit too short to drift.

- **Boundary: assess vs act.** When the ask is a question or problem description
  rather than a change request, the deliverable is the assessment. State:
  _"When the request is a question or a problem description rather than a change
  request, the deliverable is your assessment. Report findings and stop; don't
  apply a fix until asked."_
- **Ground progress claims.** On anything long-running or multi-step:
  _"Before reporting progress, audit each claim against a tool result from this
  session. Only report work you can point to evidence for; if something isn't
  verified, say so explicitly."_

## Route the model

Pick the cheapest tier that preserves the output the task needs. Set it on the
order; never switch models mid-thread (rebuilds the prompt cache, costs more).
To change tiers, spawn a fresh worker with a short handoff summary.

- **Haiku** — read-only exploration, classification, grep-and-summarize, mechanical
  leaf edits, simple extraction. (`explore` default)
- **Sonnet** — most implementation, multi-file edits, moderate reasoning.
  Default executor. (`implement` default)
- **Opus `xhigh`** — architecture, adversarial review / bug-hunting, hard
  debugging, ambiguity, anything Sonnet provably fails. (`reviewer` default)
- **Advisor** — cheap executor + Opus on genuine forks (`max_uses` cap).
- **Effort** (Opus 4.8): `xhigh` for agentic/coding, `high` for analysis,
  `medium`/`low` for routine. Cap `max_tokens`.

## Model-specific don'ts

- Don't put "show your work / echo your reasoning" in an order bound for Fable 5 —
  it triggers a `reasoning_extraction` refusal. Read `thinking` blocks instead.
- Don't over-prompt with `CRITICAL:` / `ALWAYS` caps. Normal specific language.
- Fable 5 effort: default `high`; reserve `xhigh` for capability-sensitive
  judgment. Don't reflexively max the dial.
- Don't hand Fable 5 a skill written for a weaker model verbatim — trim to intent
  - the two guardrails above.

## Token discipline

- Name the **files to inspect first**; no repo-wide scan unless blocked.
- **Don't plan unless blocked** on routine fixes.
- **One reviewable unit per order** and **one worktree per task**.
- Pass **paths, not pasted code**.
