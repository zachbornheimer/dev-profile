# Implementation Work Order

Use this as the task-specific layer. Do not paste the full construction contract
into every request; require the agent to load the canonical source.

## Required fields

```text
intent:
  The observable product outcome in one sentence.

target:
  Exact repositories, packages, product operations, and files to inspect first.

blast radius:
  What is intentionally outside the change.

construction:
  Load and follow 01-CODE-CONSTRUCTION.md.
  Load and follow 05-CONTRACTS.md when the change affects a contract boundary.
  The real production path must embody it; design-only or unused scaffolding
  does not satisfy the task.

affected product operation:
  The domain-level operation whose behavior changes, or "none — leaf change."

decision owner:
  The concept that owns the affected policy or state transition.

mutation authority:
  The sole boundary permitted to perform each consequential effect.

observed basis:
  The version/revision binding required for safe execution, or "not applicable."

inputs:
  API contracts, repository tasks, specifications, examples, fixtures, and paths
  needed for the task.

quality attributes:
  Required security properties, threat boundaries, reproducibility target,
  workload scale, service-level objective, resource ceiling, and resilience
  behavior. Use "not applicable" only with a reason.

done when:
  Behavioral end state plus structural production-path conditions.

verify how:
  Exact focused tests, full gate, architecture checks, adversarial falsification
  probes, clean-checkout reproduction, and real end-state probe.
```

## Compact implementation instruction

```text
Implement the requested outcome through the smallest complete affected domain
path. Start from the product operation and make the production flow read in
domain language. For mutable workflows, separate coherent observation, pure
decision, and faithful execution. Return consequential behavior as typed domain
data, give decisions and mutations one owner, bind effects to the observed
version, and keep infrastructure below the domain boundary. Own semantic
strings and numbers with domain constants; keep localized prose behind message
keys. Apply each affected boundary contract in 05-CONTRACTS.md. Reuse the owning
function instead of copying logic. Improve the complete affected concept without
expanding into unrelated work. Migrate affected callers and remove bypasses.
Prove both behavior and the real production architecture before reporting
completion. For relevant quality claims, load 06-QUALITY-ATTRIBUTES.md and prove
the claim against its named workload and failure boundary.
```

## Four calibration examples

### Stateful policy change

```text
publish(resource):
  observation = observe_publishable_state(resource)
  plan = decide_publication(observation)
  return execute_publication(observation.basis, plan)
```

A change to publication policy updates this complete path. It does not add a
private condition inside a queue worker.

### Leaf adapter change

```text
Catalog.list_all(query):
  page = provider.fetch(query, cursor)
  repeat until page.next_cursor is absent
  return catalog_items
```

If only provider pagination changes, preserve the `Catalog` contract and change
its adapter. Do not rebuild the product workflow.

### Existing unsafe path

```text
before:
  handler -> read + decide + write

after:
  handler -> owned_workflow
  owned_workflow -> observe -> decide -> execute
```

Move affected callers to `owned_workflow`. Remove the handler's authority to
write after the migration.

### Shared data rule

```text
script_a -> FileFacts.last_modified(path)
script_b -> FileFacts.last_modified(path, time_policy)
```

Both scripts use the same project function. If they cannot import it, improve
the package boundary instead of copying the check.

## Prompt-writing guidance

- State the outcome, scope, constraints, evidence, and completion condition once.
- Reference source files instead of copying their contents when the agent can
  load them.
- Include examples only when they clarify a boundary or correct a demonstrated
  failure.
- Prefer positive, concrete instructions over repeated prohibitions.
- Do not request hidden reasoning or chain-of-thought. Require cited evidence and
  an inspectable verdict instead.
- Put deterministic safety in permissions, hooks, lint, tests, or architecture
  checks rather than relying on prompt obedience.
