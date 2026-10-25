---
name: 35 Semantic Code and Content Linting
description: Turn team conventions that require interpretation — not mechanical syntax rules — into reviewable TypeSafe checks, leaving formal, provable rules to ordinary linters.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/concepts/use-case-map
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

A team standard can't be expressed as a mechanical rule a conventional linter can check, because it requires understanding meaning, not syntax. Use this only where a conventional linter genuinely cannot know the answer — never as a wholesale replacement for deterministic lint rules.

## What it demonstrates

The use-case map lists "Semantic code linting" among its automation use cases. Example conventions that fit this shape: error messages should tell the operator what action to take; public API names should describe user intent rather than implementation detail; release notes must distinguish breaking changes from fixes; support replies must directly address the customer's requested action; security-sensitive changes must explain their threat model. TypeSafe handles the interpretive judgment (does this text actually satisfy the convention?); code still owns file discovery, AST parsing, exact exclusions, CI behavior, and review policy.

## Steps / call shape

```text
changed artifact + explicit convention
  -> Noul/Score/Choice semantic checks
  -> code maps findings to pass / warning / review
```

A semantic lint is structured the same way as any other TypeSafe check: a `Noul` for "does this satisfy the convention," a `Score` for "how well does this satisfy the convention," or a `Choice` among a small set of violation categories — evaluated against the specific changed artifact (a commit message, an error string, a release note entry) plus the convention text as state, with the pass/warning/review policy decided in code from the returned probability or score.

## Results / numbers

The source page is a use-case listing, not a benchmarked cookbook — no numbers are published for this specific pattern. The closest quantified relatives are the citation-verification and guardrail cookbooks summarized in `31-Universal-Verification-Layer.md`, which use the identical "Noul/Choice check against explicit criteria, code decides the policy" shape.

## Pitfalls

- Do not replace deterministic lint rules with AI checks — add semantic checks only for the subset a conventional linter cannot reliably evaluate.
- Because there's no single benchmarked cookbook for this pattern, treat it as a template to instantiate and measure per-convention, not a pattern with pre-validated accuracy numbers.
- As with any TypeSafe check gating CI or review, keep the accept/warn/block policy and its thresholds in code, calibrated against your own convention and corpus rather than borrowed from an unrelated cookbook.

## Related cookbooks

- `31-Universal-Verification-Layer.md` — the same check-then-code-decides shape, applied to claims, tool calls, and generated output rather than code/content conventions.
- `36-Manual-Review-to-Confidence-Gated-Automation.md` — the same idea generalized to any human review queue, of which semantic linting is one instance.
