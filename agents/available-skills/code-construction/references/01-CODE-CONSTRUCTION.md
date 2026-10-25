# Construction contract

## Make the product legible first

Start from the operation a caller understands. Put domain names, finite states,
decisions, reasons, effects, and the top-level algorithm before adapters and
mechanisms. A reader should understand what can happen, in what priority order,
and who owns each action without reading framework, storage, queue, or provider
code.

Name every production file before you write it. Put the ledger next to the
product entrypoint as `LAYOUT.md`:

```text
path: one purpose
```

The purpose is one domain concept a reader can hold, not a helper and not a
bag of mechanisms. Group related policy into one owner. Do not create a file
per function. A purpose that names two owners is two files. English "and"
inside one concept is fine.

A ledger with more files than concepts you can hold is an inventory of
methods, not an architecture. For one product surface, start from a small
set such as:

```text
app/experience.ts: product operations; observe, decide, execute
app/domain/decisions.ts: pure plans for the product states
app/ports.ts: narrow effect contracts
app/ExperienceView: compose one screen from those owners
```

Add a file only when a new concept appears. Split a port when it names
unrelated mechanisms. Put a large inject or provide host in its own file.
Keep observe, decide, and execute in the composition root; handler files
should not each rebuild that sequence. A file that both gathers facts and
applies effects is two owners. Observation returns facts. Execution applies
a plan. Do not merge those jobs to make a shortcut.

Write this ledger first. Then write only the files it names, with only the
purpose it states.

A file whose contents do not match its purpose is a failed design. A file over
about 250 lines, or a function over about 50, means the purpose is still mixed.
Stop and rename owners. Do not split by line count while keeping the same mixed
purpose. Do not keep a leftover mega-file and call the leftover a migration
risk.

Each product operation has one obvious entrypoint. HTTP routes, commands,
webhooks, jobs, and workers adapt input and converge there. They do not implement
policy independently.

Make the algorithm visible in that entrypoint: obtain the observation, derive
the plan, and execute it. A facade whose single call hides the entire workflow is
not progressive disclosure. Helpers may implement each named phase, but the
entrypoint must show their order and data flow.

Give execution an explicit owned operation when the plan can cause effects. Do
not hide execution in a comprehension, callback, constructor, or generic service
call. The entrypoint should make the sequence and the value crossing each phase
plain to a reader.

Use simple `if`, `switch`, and early-return flow in policy order. Abstractions
must remove a concept, duplicate rule, or unsafe state—not merely add a layer.

## Separate facts, policy, and effects

Observation gathers all facts needed for one decision into a coherent domain
value. It reports facts; it does not decide eligibility or desired action.

Decision code accepts domain values and returns an explicit plan. It performs no
network, filesystem, database, clock, random, logging, queue, retry, callback, or
framework effects. Plans carry the primary decision, independent effects,
ordering or concurrency, preconditions, reasons, evidence, and observed basis
when those concepts matter.

Model plans as closed data, not callbacks or loosely related fields. Distinguish
what was proposed, authorized, attempted, observed, and verified when those are
different states. Do not report an attempted effect as a successful outcome.
When useful, include one primary decision and a collection of independent
effects, with their ordering, requirement level, preconditions, and version
basis. A list of selected records alone is not an action plan when execution
still has to invent what to do with them.

Model correlated facts as one closed state. Separate optional fields are unsafe
when only certain combinations are valid. Prefer:

```text
PriorAttempt = None | Matching(original_result) | Conflicting
```

over independent `prior_request?` and `prior_result?` fields that permit a
request without its result. Make impossible combinations unrepresentable.

Every plan field must affect execution or be removed. A field named `basis`,
`version`, `precondition`, `required`, or `authorized` is a promise that
the executor enforces. Carrying it without checking it creates false confidence.

Execution owns effects. It follows the plan and does not invent product policy.
Consequential actions revalidate their basis at the mutation boundary. Stale
work is rejected and re-observed; facts from one version never authorize a
mutation of another.

## Model the domain so misuse is difficult

Prefer closed unions, enums, value objects, constrained constructors, and
exhaustive handling. Do not represent mutually exclusive states with loose
booleans or anonymous strings.

Every semantic value has one owner: a domain constant or type, message key,
configuration value, protocol constant, or external input. User-facing prose is
rendered at the boundary from message keys and parameters. Do not create
constants for incidental syntax; the goal is semantic ownership, not constant
soup.

Raw string members are acceptable only at serialization boundaries. Domain
logic compares named members such as `Decision.Wait` or `Decision.Publish`, not
repeated string literals. Translation changes rendered messages, never control
flow values.

Names state what callers may rely on, not the current mechanism. Prefer a stable
domain guarantee such as `CurrentVersion` or `Store` over a provider token or
library name.

## Own dependencies and reuse

Code that consumes an effectful or third-party capability defines a narrow port
in its own language. Adapters translate libraries, standard-library mechanisms,
SDKs, filesystems, clocks, randomness, processes, databases, and transports into
that port. Tests use explicit fakes. Mocking library internals is a warning that
the boundary is misplaced.

Facade even a standard-library capability when it is effectful, nondeterministic,
hard to test, likely to change, or carries product meaning. Do not facade pure,
stable primitives without a reason.

Search before creating. If two scripts or workflows interpret the same data or
rule, they call the same owned function with explicit parameters. A subtle
variation extends the shared abstraction; it does not justify a copied special
case. Every policy, transition, retry rule, mutation, and invariant has one owner.

Make the owned path easier to reuse than to bypass. If the same pattern recurs,
name the missing domain concept and centralize it. If the pattern is forbidden,
encode the rule in a focused check with positive and negative fixtures instead
of relying on repeated review comments.

## Keep units easy to change

Prefer one reason to change per unit. About 250 lines per production file, 50
lines per function, three parameters, and shallow nesting are review signals,
not excuses for mechanical splitting. Exceed them only when the cohesive result
is clearer than the split.

Apply these signals across the complete production path. Do not make the public
entrypoint small by concentrating its former responsibilities in one oversized
service, composable, manager, helper, or adapter. A large new unit is evidence
that ownership still needs to be separated unless its contents genuinely form
one indivisible concept.

Comments explain current invariants, guarantees, surprising ordering, and why a
seemingly simpler approach is unsafe. Names and types explain what code does.
History belongs in commits, issues, and design records.

Write plain language in code, comments, errors, and documentation. Use short
active sentences and one term for one meaning.

## Test the same architecture production uses

Pure decisions are tested with plain domain values and no infrastructure mocks.
Shell tests prove observation, faithful plan execution, precondition checks,
non-duplication, and adapter translation. Public tests run the installed or built
artifact and assert output, status, and final state.

Inspect structure separately from behavior. Passing tests do not prove that the
production path uses the intended entrypoint, that a facade is real, or that a
competing mutation path is gone.
