---
name: verifiable
description: Use when output (number, figure, decision, recommendation) travels to a client, finance team, or leadership, or for clinical, legal, regulatory, or audit contexts — where plausible-but-wrong is unacceptable.
---

# Verifiable AI

In high-stakes domains — finance, healthcare, insurance, legal — a plausible answer
that is wrong is worse than no answer. Verifiability is an architectural
requirement, not a feature you add later.

## The core split: reasoning vs. execution

The model interprets. A deterministic engine computes.

```
Claude:           interpret the question → decompose intent → produce a structured
                  execution plan → flag ambiguity → hand off to execution layer
Deterministic     apply the formula → resolve the fiscal period → compute the ratio
layer:            → pull the verified source → assemble the result
```

**Claude never computes the number.** It figures out _what_ to compute and _where_
to find the inputs. The execution layer does the provably correct operation.

This is how Kepler Finance processes 26M+ SEC filings: Claude reasons about which
line items to pull and reconciles terminology; a deterministic engine pulls them,
computes the ratio, and links back to the exact filing, page, and line item.
Carta Healthcare does the same for clinical abstraction: Claude reasons about which
clinical context matters; the pipeline enforces the time boundary and surfaces the
supporting evidence.

## The four rules

### 1. Separate reasoning from execution

Every operation that must be provably correct — computing a ratio, resolving a
fiscal period, finding a lab value before a procedure timestamp — runs in a
deterministic execution environment. Claude invokes it; Claude does not implement
it.

Design the deterministic layer as idempotent skills: the same input always produces
the same output. That's how you audit, replay, and test them.

### 2. Escalate ambiguity; never resolve it silently

When a term has two defensible interpretations, the model must stop and ask —
not pick one and continue. One wrong assumption early in a financial analysis
breaks everything downstream. _"That behavior matters more than any benchmark
score."_ (Kepler)

Build hard boundaries into the context: structured domain definitions, explicit
rules about what to resolve vs. what to escalate. The model's job is to surface
the fork, not to hide it.

### 3. Provenance footer on every output

Every produced figure or decision must carry a provenance trail the reader can
audit in two clicks:

```
Source tier:   SEC filing / EHR chart / verified registry
Freshness:     2026-Q1 10-K / procedure date 2026-03-15
Owner:         Kepler retrieval layer / Carta Lighthouse
Reviewed ✓:    abstractor sign-off / analyst trace
```

Professionals are trained to verify everything. Provenance must shape the entire
system, not get added at the end. SOC 2 / HIPAA / audit logging follow from the
same discipline.

### 4. Content engineering over prompt engineering

_"Prompt engineering optimizes a call. Content engineering optimizes the system
around it."_ (Kepler)

The right context — precisely defined tasks, structured domain knowledge, correct
time boundaries, right documentation in the right priority order — matters more
than prompt wording. A perfectly written prompt with bad context gives bad answers.
A plain prompt with the right context delivers.

Before tuning the prompt, ask: does the model have what it needs to reason, or is
it figuring things out from whatever's available? Fix the context construction
first.

## Architecture checklist

Before shipping any high-stakes AI output pipeline:

- [ ] Claude's job is reasoning and interpretation only — not computation
- [ ] Every provably-correct operation runs in a deterministic execution layer
- [ ] Ambiguity escalates to a human; the model does not pick and continue
- [ ] Every output carries a provenance trail to its source
- [ ] Skills / workflow stages are idempotent (same input → same output)
- [ ] Evaluation pipeline tests each stage independently AND the full pipeline
- [ ] Audit logging, access control, and siloed environments are built in from day 1
- [ ] A failing test traces to: Claude's reasoning, the context provided, OR the
      downstream execution — one of the three, cleanly

## Model matching (from Kepler's practice)

Match model capability to stage complexity:

| Stage                                                              | Model                    | Why                                                             |
| ------------------------------------------------------------------ | ------------------------ | --------------------------------------------------------------- |
| Decompose intent, resolve ambiguity, produce execution plan        | Opus                     | Complex reasoning; must hold a long plan together without drift |
| Constrained high-throughput tasks (extraction, classification)     | Sonnet                   | Speed + cost; the task is well-scoped by the time it arrives    |
| Specialized recall tasks (taxonomy mapping, label standardization) | Fine-tuned / specialized | 94% accuracy vs 38-46% for general frontier models              |

Test every prompt change, model upgrade, and context modification against
thousands of known-correct cases before production. When a test fails, you need
to know: was it Claude's reasoning, the context, or the execution layer?

## Gotchas

- **"The model can't be the whole system."** It's one stage in a pipeline. Treat
  it that way at the architecture level, not as an afterthought.
- **Silent wrong answers erode trust permanently.** In finance, a silent regression
  is how you lose a client. In healthcare, it's how you corrupt a registry.
  Build evaluation BEFORE you tune prompts.
- **Provenance can't be retrofitted.** Every design decision that doesn't account
  for traceability makes audit harder. Start with it.
- **Ambiguity is data.** When the model surfaces an ambiguous term, that's a
  signal that the domain ontology needs a clearer definition — fix the definition,
  not just the answer.
- **Domain expertise shapes the prompts, not the other way around.** Carta's
  clinical abstractors hand engineers long explanations of how a specific data
  point works in practice. That explanation IS the prompt revision. What used to
  take months of data science work ships in a week when the domain expert's
  explanation flows directly into the context.
