# ui-decompose

A Claude Code skill that turns a design implementation request into an exhaustive, implementation-neutral UI decomposition and gates final output behind deterministic validation plus fresh adversarial source review.

## Install

Copy `ui-decompose` to either:

- `~/.claude/skills/ui-decompose`; or
- `<project>/.claude/skills/ui-decompose`.

## Invoke

Paste the same request you would otherwise give a design implementation agent:

```text
/ui-decompose

Use the claude_design MCP (...) to import this project:
...

Focus on these files:
- popup-direction.html

Implement: popup-direction.html
```

`Implement:` defines decomposition scope. The skill does not implement UI or choose a target UI kit.

## Workflow contract

1. A fresh decomposition agent inspects the real source and writes schema-valid JSON.
2. Deterministic validation checks request binding, scope roots, source coverage, graph integrity, evidence-bearing entities, state/interaction invariants, and zero unresolved source uncertainty before review.
3. Up to three fresh adversarial reviewers independently inspect source. Each review is SHA-256-bound to the exact request/decomposition and must provide a source-evidenced audit entry for every surface, node, state, and interaction.
4. When review requests changes, a fresh correction agent must disposition every finding in a schema-valid correction report. The corrected decomposition is revalidated before the next review.
5. Final Markdown is generated only after a fresh review returns no findings.

The contract strongly enforces process and artifact completeness; it does not pretend a schema can mathematically prove that arbitrary source tooling exposed every possible hidden state.

## Output

On success:

- `ui-decomposition.md` — generated human-readable specification with certification summary.
- `.ui-decompose/run-*/ui-decomposition.json` — machine-readable source of truth.
- `.ui-decompose/run-*/review-N.json` — adversarial audit records.
- `.ui-decompose/run-*/correction-N.json` — correction dispositions when needed.

On failure, the working directory preserves the exact blocker and prior artifacts. The final Markdown is not emitted as certified.

## Test

```bash
python3 -m unittest discover -s tests -v
```

Requirements: Python 3 and `jsonschema`.
