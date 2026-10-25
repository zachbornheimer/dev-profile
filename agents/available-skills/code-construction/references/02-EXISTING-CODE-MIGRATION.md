# Existing-code changes

Improve the smallest complete domain path named by the request. If the request
names a whole module, file, or product surface, that surface is the complete
path. Do not require an unrelated rewrite, do not migrate only a few selected
methods from a named module, and do not bolt behavior onto an unsafe path
merely to minimize the diff.

A refactor transfers ownership. The new abstraction directly owns the migrated
behavior, and the production path calls it. A wrapper, proxy, compatibility
object, generic state bag, or dynamic call adapter that preserves the old owner
is not a completed refactor. Migrate callers and remove the superseded owner.

Rethink the affected design through the construction contract before moving
code. Treat the legacy implementation as evidence of behavior, dependencies,
and constraints—not as the target module map. Start again from the product
operation, domain states, decisions, effects, contracts, and owners. Write
`LAYOUT.md` for the named module as `path: one purpose` before extracting
files. Group the legacy methods into a few holdable concepts. Do not make a
file for each old method. Then place each behavior under the owner named in
that ledger.

A size, SRP, SOLID, or DRY violation in the result means the layout named the
wrong owners. Fix the ledger. Do not keep the mixed file and warn about it.
A swarm of tiny files with the same mixed knowledge is the same failure.

Do not select old methods, fields, or blocks and move them together merely
because they were adjacent. Preserve intentional behavior while replacing the
old organization. Extraction without reconsidering responsibility, dependency
direction, state shape, and reuse only relocates the maintenance problem.

1. Protect intentional public behavior with focused tests. For a defect, first
   prove a failing test against the defect.
2. Name the owning product operation, decision owner, mutation authority, and
   version basis.
3. Inventory all affected reads, decisions, writes, callers, retries, contracts,
   library boundaries, and duplicated interpretations.
4. Create one coherent observation, pure decision, explicit plan, and owned
   executor for the affected path.
5. Route affected callers through that path and remove superseded paths.
6. Add success, failure, stale-state, and contract tests in proportion to risk.
7. Verify public behavior and production structure separately.

For a large legacy module, identify its cohesive responsibilities before
extracting files. Move domain policy to pure functions, reusable effects and
stateful behavior to composables or equivalent application modules, and visual
regions with clear input/output contracts to components. Keep orchestration at
the product-facing entrypoint. Do not turn one large file into many files that
still share hidden state or duplicate policy.

Apply SRP, SOLID, and DRY to the resulting design:

- each file and type has one cohesive owner and one primary reason to change;
- high-level product policy depends on domain contracts, not framework,
  provider, storage, or transport details;
- consumers receive narrow capabilities and do not depend on methods they do
  not use;
- real variations extend an owned abstraction without modifying unrelated
  callers;
- each rule, interpretation, state transition, and effect policy has one owner;
- shared behavior is easier to reuse than to copy.

A thin entrypoint does not compensate for a new oversized service, composable,
manager, utility, or runtime module. Apply the same ownership and size review to
every production file. If most legacy responsibilities remain concentrated in
one new unit, the refactor is incomplete.

Before calling a refactor complete, inspect every resulting production file. A
remaining oversized legacy owner, generic runtime or state bag, dynamically
bound method collection, or concentrated replacement owner is a failed
refactor. Those leftovers are incomplete work, not a migration risk. If the
requested ownership transfer is unfinished, report partial progress.

Preserve behavior through characterization tests and contract tests at the
existing public boundary. When the available fixture cannot prove behavior,
label that gap instead of inventing certainty. Replace obsolete framework
patterns as one vertical path so the production route uses the new structure;
do not leave a decorative modern layer beside the legacy owner.

A temporary migration seam is acceptable when named and bounded. Two permanent
owners are not. Leave each touched concept easier for the next developer or
agent to understand and modify.
When the request is new work, still look for cleanup on the path you open. Resolve mixed owners, copied policy, and unclear homes before you call the new path done. New code is not allowed to walk past debt it touches.
