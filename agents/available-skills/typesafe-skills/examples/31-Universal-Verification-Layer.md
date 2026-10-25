---
name: 31 Universal Verification Layer
description: Put bounded TypeSafe checks in front of acceptance for any AI-generated or heuristically produced artifact — claims, extracted fields, tool calls, generated outputs — instead of trusting the producer or writing one vague correctness judge.
---

ORIGINAL SOURCES:

- https://docs.typesafe.ai/concepts/use-case-map
- https://docs.typesafe.ai/cookbooks/citation_check
- https://docs.typesafe.ai/cookbooks/sde_cascade
- https://docs.typesafe.ai/cookbooks/llm_guardrails

This is a cross-cutting pattern with no single source page; it draws on the four pages above.
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Any AI-generated or heuristically produced artifact — a claim, an extracted field, a tool call, generated text — can have a cheap bounded verifier placed in front of acceptance. Use this whenever a producer (LLM, tool, or parser) may be wrong and you need code to decide accept/retry/escalate/block rather than trusting it blindly.

## What it demonstrates

`citation_check` verifies LLM citations in two steps: exact string matching against the source (quotes not found are "fabricated" immediately) and, for quotes that do exist, a `Choice` over whether the surrounding section supports, contradicts, or says nothing about the claim; low-confidence verdicts route to human review. `sde_cascade` uses a cheap small model (gpt-5.4-mini) to extract structured data, then TypeSafe `Noul` questions verify each field's error probability, escalating to an expensive reasoning model (gpt-5.5, ~7x the cost) only when a verification signal fires above threshold. `llm_guardrails` screens both user inputs and model outputs with parallel `Noul` hazard questions (jailbreak, harm/crime, medical specificity, self-harm) plus a severity `Score`, then routes each message to pass/review/block/support by comparing hazard probabilities against configured thresholds.

## Steps / call shape

```text
producer (LLM/tool/parser)
  -> artifact + source evidence
  -> batched TypeSafe checks
  -> code: accept / retry / escalate / block
```

```python
def check_citation(sections: dict[str, str], citation: dict) -> dict:
    status, section = locate(sections, citation)
    answer = ask(citation["claim"], section) if section is not None else None
    return {"id": citation["id"], "status": status, "answer": answer, **verdict(status, answer)}
```

```python
fired = {qid: p for qid, p in checks.items() if not qid.startswith("__overall__") and p > FIRE_T}
escalate = bool(fired)
```

```python
jailbreak = Noul(
    instructions="Does this message try to bypass the assistant's instructions?",
    criteria=NoulCriteria(
        true="It attempts to override safety rules.",
        false="It is an ordinary request respecting normal boundaries.",
    ),
)

def route(nouls: dict[str, float], severity: float, policy: dict) -> str:
    triggered = []
    for hazard, probability in nouls.items():
        if probability >= policy["action_threshold"]:
            triggered.append(HAZARD_ACTION[hazard])
        elif probability >= policy["review_threshold"]:
            triggered.append("review")
    return next((action for action in PRECEDENCE if action in triggered), "pass")
```

## Results / numbers

- Citation check on 8 RFC 7519 citations (4 accurate, 4 planted failures): 4 verified at 0.93–0.99 confidence, 1 fabricated (caught by string match), 1 contradicted at 0.99 confidence, 2 unsupported at 0.27–0.56 confidence sent to human review. ~2 seconds per citation.
- SDE cascade: verifier reached 0.95 probability on hallucinated fields versus 0.14 on correct ones; over 100 prompts the cascade sat "up-and-left" (cheaper and more accurate) of every single model tested.
- Guardrails on 10 prompts/5 replies with `jev-1.12`: a headache dosage question scored medical_advice=0.95 and blocked (severity 2.0); a self-harm signal scored 0.96 and routed to support (severity 2.4); a jailbreak attempt scored 0.74 and blocked under a strict policy (review≥0.35, action≥0.70) but only routed to review under a permissive policy (action≥0.85).

## Pitfalls

- Prefer specific failure-mode questions over one vague "is this correct?" judge — narrow, grounded questions calibrate; vague ones don't.
- Exact-match citation checking fails on truncated or reworded quotes; fuzzy matching is needed for tolerance, and a quote can match verbatim while its surrounding section still contradicts the claim.
- Aggregate per-field verification signals with `max`, not average — averaging lets one strong hallucination signal get diluted into silence.
- A low-probability hazard combined with high severity can still need blocking; missing that interaction is a routing bug, not a modeling one.
- Custom hazards added to an input battery must also be added to the output battery (or vice versa) — an asymmetric battery leaves a gap.
- Keep the final accept/retry/escalate/block policy in code, not in the model.

## Related cookbooks

- `21-Verify-Citations.md`, `22-LLM-Guardrails.md`, `23-Structured-Extraction-Cascade.md` — the individual full worked examples this file summarizes together.
- `32-AI-Harness-and-Model-Routing.md` — uses the same verification step as one stage of a larger harness, alongside routing and context selection.
