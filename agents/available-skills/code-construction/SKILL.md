---
name: code-construction
description: Use when creating, changing, refactoring, or reviewing code. Guides code toward visible domain workflows, a functional core and imperative shell, explicit ownership, reusable dependency boundaries, version-safe effects, and proven repository, security, and reliability contracts. Applies to new projects, features, fixes, APIs, scripts, shared utilities, dependency integrations, repository automation, and structural review. Skip behavior-neutral text and leaf configuration edits.
---

# Code construction

The production code must embody these rules. A design document, unused facade,
test-only architecture, or passing general test suite is not compliance.

## Always load the contract

Before creating or changing code, read every contract file:

1. [01-CODE-CONSTRUCTION.md](references/01-CODE-CONSTRUCTION.md)
2. [02-EXISTING-CODE-MIGRATION.md](references/02-EXISTING-CODE-MIGRATION.md)
3. [03-STRUCTURAL-REVIEW.md](references/03-STRUCTURAL-REVIEW.md)
4. [04-IMPLEMENTATION-WORK.md](references/04-IMPLEMENTATION-WORK.md)
5. [05-CONTRACTS.md](references/05-CONTRACTS.md)
6. [06-QUALITY-ATTRIBUTES.md](references/06-QUALITY-ATTRIBUTES.md)
7. [07-LANGUAGE-QUALITY.md](references/07-LANGUAGE-QUALITY.md)

Do not skip a file because the work looks new, small, or language-specific.
Apply 07 only for languages actually touched, but still read the file.

## Required construction sequence

Name owners before writing files. Write `LAYOUT.md` beside the product
entrypoint as `path: one purpose` lines. Name concepts a reader can hold, not
every method you found. One product surface usually needs a composition root,
pure decisions, narrow ports, adapters, and a few views. If the ledger is a
long method list, rewrite it before you write code.

Implement only that ledger. Observe, decide, and execute belong in one
composition root. Do not copy that sequence into every handler file. If a
finished file does not match its purpose, or exceeds the size barometer, the
angle is wrong — rename owners and rewrite the ledger.

For a workflow that reads mutable reality and may cause effects, build and keep
this production path visible:

```text
product operation
  -> observe coherent facts
  -> decide a typed plan with pure code
  -> execute that plan through owned ports
  -> infrastructure adapters
```

The production entrypoint itself must make those phases visible. A reader should
not need to enter a service class or trace generic helpers to discover the
algorithm. Use a direct shape such as:

```text
product_operation(input, dependencies):
    observation = observe(input, dependencies)
    plan = decide(observation)
    return execute(observation, plan, dependencies)
```

The names are illustrative. Use the product's language. Do not create ceremonial
phases that the real trigger bypasses.

Call a named execution operation from the entrypoint when effects occur. A loop,
comprehension, callback, or adapter call performed inline is not an explicit
execution phase, even if it eventually invokes the correct port.

Before polishing infrastructure, prove one ordinary vertical path through the
public entrypoint. Add each boundary or invariant with a focused adverse test,
then rerun the ordinary path. A safeguard that breaks normal use has failed.

Treat requested names, invocation forms, inputs, outputs, status codes, and
side effects as acceptance contracts. Do not replace them with a cleaner
interface unless the request authorizes that change. Test the exact requested
entrypoint—not an internal helper, alias, wrapper, or invented alternative.

## Completion evidence

Before reporting completion:

- trace the real trigger to its mutation;
- identify the decision owner and mutation authority;
- search for bypasses and duplicate implementations;
- publish `LAYOUT.md` and confirm every production file matches one purpose;
- rewrite the ledger if it lists more owners than a reader can hold;
- inspect every resulting production file for mixed ownership, duplicated
  knowledge, reversed dependencies, and responsibility concentration;
- treat a remaining oversized owner, generic runtime or state bag, dynamically
  bound method map, or concentrated replacement module as incomplete work, not
  as a documented migration risk;
- run focused success, failure, and boundary tests;
- invoke every requested public entrypoint with its exact documented shape;
- invoke it through the repository's normal fresh-shell environment, without a
  private build path or undocumented manual activation;
- run the repository's complete public gate twice;
- exercise the built or installed public artifact outside the source tree;
- report anything not directly proven as `NOT PROVEN`.

When a deterministic operation has been performed more than once, or will be
repeated by agents, give it one reusable script or repository task. The script
owns the sequence, validation, evidence, and safe defaults. Agents call it; they
do not reconstruct the procedure from prose on every run.
