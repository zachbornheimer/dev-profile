# Structural Review Gate

Passing tests is necessary but does not prove that production code embodies the
construction contract. Review behavior and structure separately.

## Evidence first

Before rendering a verdict:

1. Identify the changed product operation and affected production entrypoints.
2. Trace at least one real path from external trigger to consequential mutation.
3. Cite the production symbols that observe, decide, plan, execute, and validate
   the version basis.
4. Search for alternate decision or mutation paths.
5. Inspect tests and architecture enforcement separately from implementation.
6. Check the API contract and repository task contract when they apply.
7. Identify each consequential invariant and run a probe designed to falsify it.
8. Apply `06-QUALITY-ATTRIBUTES.md` when the change makes a quality claim.

Do not infer compliance from directory names, interfaces, comments, or an
implementation report.

## Review questions

### Product expression

- Is the product operation obvious?
- Does its top-level flow read as the domain algorithm?
- Can a reader understand behavior before reading infrastructure?
- Do all relevant external triggers converge on the same paved workflow?

### Observation and versioning

- Are decision facts gathered before policy runs?
- Do those facts describe a coherent and honestly named observation?
- Does the plan carry the exact basis used to decide?
- Is that basis checked immediately before consequential mutation?
- Can state change between the check and mutation?
- Does the implementation use an atomic conditional operation, or validate and
  safely recover after mutation?
- Does a mismatch reject the whole stale plan and cause re-observation?

### Decision purity and plans

- Can policy be tested with plain domain values and no infrastructure mocks?
- Does it return an explicit, exhaustive domain plan?
- Are reasons, evidence, effects, ordering, dependencies, and preconditions
  visible when relevant?
- Are callbacks, SDK objects, logging, retries, or hidden policy absent from the
  pure core?
- Does execution follow the plan without inventing policy?

### Ownership and authority

- Does each important decision, transition, retry policy, and invariant have one
  domain owner?
- Does each mutation have one narrow mechanical authority?
- Are adapter responsibilities limited to translation and protocol mechanics?
- Can any handler, worker, hook, or helper bypass the owner?

### Domain modeling

- Are finite states and actions represented by closed types?
- Do semantic strings and numbers have domain owners?
- Is user-facing prose represented by message keys and typed parameters?
- Are names promises the implementation actually keeps?
- Are invalid or ambiguous state combinations difficult to represent?

### Contracts

Apply `05-CONTRACTS.md` to each affected boundary.

- Is the promise, owner, canonical definition, and compatibility policy clear?
- Do the real provider and consumers use the same contract?
- Do contract tests exercise that production path?
- Can any caller bypass the contract or maintain a duplicate interpretation?

### Composition

- Does every abstraction protect a real concept, invariant, ownership boundary,
  or test seam?
- Did duplication reveal a missing owner, or is repeated syntax intentionally
  clearer than a shared abstraction?
- Do comments explain current contracts and safety constraints rather than
  syntax or history?
- Did the change remain within the smallest complete affected domain path?
- Does each source file normally stay at or below 250 lines?
- Does each interaction leave the affected concept easier to change next time?

### Production reality

- Does production call the reviewed workflow?
- Do tests exercise that same workflow?
- Are alternate legacy paths removed?
- Are deterministic invariants enforced by types, lint, architecture tests,
  permissions, or hooks where possible?
- Was the real end state observed rather than inferred from a unit test?

### Quality attributes

- Can a clean checkout reproduce setup, tests, and build from committed inputs?
- Are runtimes and dependencies locked according to repository policy?
- Does the security gate inspect generated and untracked files that can enter an
  artifact or commit, rather than only files already tracked by Git?
- Does each security tool fail closed when unavailable or misconfigured?
- Do scale claims name the workload, distribution, service-level objective, and
  resource ceiling?
- Do benchmarks or analytical models exercise the limiting resource and failure
  modes rather than only a small happy-path fixture?
- Do adversarial probes cross the exact seam where a claimed invariant could
  fail, including changes between validation and mutation?
- Does repeated verification start from independent clean state and produce the
  same observable result?

## Verdict

Return one of:

- **PASS:** Production behavior and structure satisfy the contract, with cited
  evidence.
- **FAIL:** At least one structural or behavioral requirement is violated. Cite
  the bypass or unsafe path and state the smallest root-level correction.
- **NOT PROVEN:** Required production-path evidence is unavailable. State exactly
  what must be inspected or executed before a verdict is possible.

Do not downgrade a structural safety failure to style feedback merely because
tests pass.
