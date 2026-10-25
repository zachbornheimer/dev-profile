---
name: code-style
description: Use when writing or reviewing code — approval bar, atomic composition, facades, WHAT-not-HOW names, no magic values, small units. Language footguns in references/. Load on any non-trivial code read or edit.
---

# Code Style

You already know the languages. This skill is the **code Zach approves** bar —
composition + the defaults models break — not a restatement of the language.

**Before writing or reviewing non-trivial code, read**
`references/approval-dossier.md` (atomic composition, jazz subtraction, checklist)
and `references/domain-composition.md` (ownership naming, comments-as-diagnostic,
invariants-in-types, progressive disclosure, effects/authority, deletion test).
For full craft/taste philosophy load `bar`. For language footguns:
`references/<lang>.md` and `references/gotchas.md`.

## Composition (required approach)

Build **concepts at the right abstraction** from **atomic elements**. Each atom
is well-constructed, performant, testable, observable, and maintainable
(including by AI — decipherable names, self-documenting flow, comments only
when they must exist).

- **Jazz subtraction:** every line/comment/abstraction earns its place or is cut.
- **≤2 motives** per change; childlike surface, intricate interior.
- **Atom stack:** values/types → pure functions → facades → policies → workflows.
- **Missing-concept signal:** file > ~250 lines or function > ~50 → extract a named concept, don't compress.

## The defaults you break (lint-enforced where possible — don't fight the gate)

- **Facade every system boundary.** No direct `os` / `time` / `http` / `rand` /
  `env` / file calls — inject them. Highest-leverage testability pattern there is.
  If you catch yourself writing a direct system call, create the facade first.
- **Names describe WHAT, not HOW.** `Store` not `SQLiteStore`, `Walk` not
  `ParallelWalk`. Suffixes only for behavioral differences callers must know.
- **No magic values.** Every number and string has a name; every operational value
  (timeout, limit, buffer size) is configurable.
- **Small units are the design signal.** File > 250 lines → the abstraction is
  wrong; find the missing concept and extract it. Function > 50 lines → doing too
  much. Nesting > 3 → flatten with early returns. Params > 5 → group into a struct.
- **Errors carry context.** Never bare `return err` / `raise` / `throw` — say what
  operation failed and on what input. Log OR return, never both.
- **DRY.** Search the codebase for an existing helper before writing a new one.
- **Delete dead code.** Unused or commented-out → gone. Git has history.
- **Comments only when required.** Invariants types can't express, non-obvious why
  (and what was rejected), safety/ordering constraints, external protocol quirks.
  Never narrate the next line. If deleting the comment wouldn't cause a wrong
  irreversible action, cut it.

## The "and" test

If describing a function, file, or package needs the word "and", split it.

## Two bars at once

Rigid interior (facades, SRP, tests) AND idiot-proof exterior (honest state, great
defaults). Never trade one for the other. See always-on `code-standards` and `bar`.

## Modernize what you touch

Use the current idiom for the language version in use; run the language's standard
modernizer. Match the surrounding code's density, naming, and idiom — write code
that reads like the code around it.

Load the language file for footguns: `references/gotchas.md` has the short list.
For Go specifically, read `references/go.md` (binary versioning, ruleguard,
concurrency, nolint, package naming). For cross-language universal gaps (review
severity prefixes, TODO format, trust-the-runtime, data-structure tables), read
`references/standards.md`.
