# Language and framework quality

Use the repository's pinned language version, formatter, linter, type checker,
test runner, and established conventions. These notes supplement that contract;
they do not justify replacing working repository standards.

## Python

Use modern type syntax and specific exception types. Prefer immutable value
objects for observations, decisions, and plans. Keep filesystem, clock, process,
environment, network, and randomness effects behind narrow consumer-owned
ports. Use `pathlib` for path values, but preserve raw path identity when a
security check depends on how the path was supplied. Do not add a validation
framework when a small typed constructor owns the invariant clearly.

## Go

Pass `context.Context` through blocking and remote operations. Define small
interfaces at the consumer boundary; return concrete types from providers.
Wrap errors with operation context while preserving errors that callers must
classify. Avoid package globals, unbounded goroutines, copied synchronization
values, and hidden background work. Run race tests for concurrent behavior and
make shutdown, ownership, and backpressure explicit.

## TypeScript and JavaScript

Use strict TypeScript for production domain logic. Avoid `any`; accept `unknown`
at external boundaries and narrow it once. Use closed discriminated unions,
named semantic members, exhaustive handling, and immutable data where practical.
Separate transport schemas from domain types. Do not use effects to represent
state that can be derived directly.

## Vue

For Vue 3, use the Composition API and `<script setup lang="ts">` unless the
repository has a documented constraint. Components own presentation and user
interaction for one cohesive region. Composables own reusable stateful behavior
and effects. Pure domain modules own policy. Keep props, emits, slots, loading,
empty, error, and disabled states explicit. Do not destructure reactive values
in a way that loses reactivity. Remove obsolete Vue 2 mixins and Options API
ownership from the migrated vertical path rather than wrapping them invisibly.

## Configuration

Treat JSON, TOML, YAML, and environment variables as public input. Give them a
schema, validate once at the boundary, document units and defaults, reject
unknown or unsafe values when appropriate, and keep secrets out of committed
files. Pin tool and schema versions when reproducibility depends on them.

## Shell

Use shell for short orchestration around existing commands. Prefer Python or Go
when logic is reusable, structured, concurrent, or substantial. Quote values,
fail on errors and unset variables where the shell supports it, use cleanup
traps, bound external calls, and keep data processing out of fragile pipelines.
