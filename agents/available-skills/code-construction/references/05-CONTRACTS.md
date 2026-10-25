# Boundary contracts

A contract is a promise across an ownership boundary. Give it one canonical
owner, named consumers and providers, explicit inputs, outputs, errors,
invariants, compatibility rules, and tests through the real boundary.

Extract an acceptance ledger from the request before implementation: exact
public names, invocation form, required and optional inputs, output shapes,
status or exit meanings, and observable effects. Preserve that contract unless
the request explicitly changes it. A consolidated command with subcommands is
not equivalent to two requested commands; an internal function call is not an
installed-artifact test.

## APIs

For HTTP APIs, author the OpenAPI contract before handlers and clients. Lint the
contract, generate types and clients where practical, and test implementation
conformance. Define authentication and authorization, validation, stable error
envelopes, pagination and limits, timeouts, idempotency for retried mutations,
versioning, deprecation, and compatibility. Avoid leaking database or provider
shapes through the public model.

For functions, commands, events, and files, apply the same discipline: one
schema or typed source of truth, explicit status and failure meanings, input
validation at the boundary, and compatibility tests for independently changing
consumers.

Validate a contract's meaning through its real parser, validator, consumer, or
public behavior. Searching source text for expected words proves only that the
words exist. It does not prove that an OpenAPI document, schema, configuration,
migration, generated artifact, or protocol contract is valid or implemented.

Contract tests invoke the exact public name and shape from outside the source
tree. Do not test an easier substitute and claim the requested interface works.
Run the test through the repository's documented fresh-shell environment. A
binary that works only through a private build directory, virtual-environment
path, source import path, or undocumented activation step is not yet a usable
public entrypoint.

## Repository

Apply this section when the request creates a repository or changes repository
automation. An isolated module refactor is not a new repository. Do not invent
`mise` tasks, lockfiles, package manifests, scanners, or CI around a fixture
unless the request asks for a complete project.

Use the repository's existing task runner. For a new repository, expose honest
`setup`, `fmt`, `lint`, `typecheck`, `test`, `scan`, `build`, `doctor`, and `ci`
tasks through `mise`. Pin runtimes and tools, commit dependency locks, and make
Lefthook delegate to those tasks. `ci` is the complete non-mutating gate, not a
friendly subset.

`setup` recreates the environment from committed inputs. `doctor` diagnoses
missing prerequisites. `build` creates the real distributable artifact. `scan`
must scan the relevant committed, generated, and untracked files and fail when a
safe synthetic finding is inserted. A task name is a claim and must be verified
against an intentional failure.

The repository environment must expose installed project commands after setup.
For example, `mise exec -- product-command` should work in a fresh shell when
`mise` is the repository contract. Do not require users or automation to know a
tool-private executable path.

Run setup and CI in a clean copy. Build twice when reproducibility is claimed,
compare normalized artifacts, and smoke-test the artifact outside the source
tree.

## Dependencies and shared code

Pin direct tools and development dependencies when the ecosystem supports it.
Keep runtime dependencies minimal, but do not reimplement a mature library to
avoid a dependency. Access libraries through consumer-owned ports or facades so
tests remain clear and replacement does not reshape the domain.

A restriction on shipped runtime dependencies does not restrict development and
verification tools unless the request explicitly restricts all dependencies.
Prefer a mature, pinned validator, scanner, linter, generator, or test tool over
a partial local reimplementation. Keep repository tools out of the shipped
runtime dependency graph.

Make shared behavior easier to call than to copy. Repeated manual commands and
agent procedures become idempotent scripts or repository tasks with validation,
timeouts, useful errors, and preserved evidence. Documentation points to the
script instead of duplicating its steps.
