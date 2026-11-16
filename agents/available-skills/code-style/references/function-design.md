# Function design

How to design one function: what it may touch, what its signature says, and
what its body contains. Source: the talk "How to write the perfect function"
(youtube 2OMRWPOSw9s), filtered through this repo's bar. Examples are C++ in the
talk; the rules are language-neutral. Structure-level ownership (files, ports,
observe/decide/execute) stays in `code-construction`; this file is the unit
beneath it.

## 1. Honest vs dishonest

The test is the signature, not purity.

- **Honest:** reads and writes the outside world only through its arguments. The
  caller controls its behavior completely. In-place `sort` is honest: it mutates
  only memory it was handed, is deterministic, and is testable.
- **Dishonest:** the signature hides an input or output (global state, clock,
  random, env, files, network, screen). `get_time()` is dishonest even though it
  mutates nothing.
- Dishonesty is infectious: an honest function that calls a dishonest one is
  dishonest. Honest functions therefore sit at the leaves; inject dishonesty at
  the outermost layer.
- Name must not promise more honesty than the body has. A getter named
  `required_assets()` that silently filters by global "already loaded" state is a
  bug generator.

Use this test in place of "pure / no side effects" when judging decision code. It
admits in-place algorithms and output parameters, and it rejects hidden reads.

Refactor shape: pull the honest core into its own function that returns the
whole result, test it, and leave the effectful shell as a thin caller. If the
full result is too big to hold, take the effect as a parameter
(`for_each_x(input, visit)`) or return an iterator; build the collecting form on
top of it. A callback form needs a stated policy for early exit and errors.

### Randomness and time

Take the generator or clock as a parameter. Seed it once at the top: from the
OS or clock for a real run, from a fixed seed for tests, replays and bug
reports. Passing the global is still allowed, which keeps today's behavior and
the option to change it. A global baked into the body cannot be recovered later.

## 2. Signatures are for the caller

- **No unexplained boolean flags** and no long positional lists of same-typed
  values. Use a named argument struct or distinct types. A struct that exists
  only to carry arguments is fine.
- **Do not require a whole object when you need one field.** Take the field.
- **Do not over-constrain a parameter.** Ask for the weakest type the body uses:
  a slice or view instead of a concrete container, an iterable instead of a
  slice if the body only loops. Ask for a strong guarantee (contiguous,
  ordered) only when the body needs it, and then ask for it in the type. Stop
  short of generic signatures that make errors unreadable.
- **Encode "call A before B" as a value.** A returns a receipt (for a mutex, the
  lock object) that B takes. B then cannot run without A, and the unnamed
  temporary lock that unlocks immediately fails to compile.
- **Encode invariants in a type, not in the body.** If a function needs a unit
  vector, a non-empty list, or a validated address, take that type. Construction
  is the only place that checks, and it fails there. The body loses its
  assert, its optional return, and its silent NaNs, and the caller, who knows
  more, decides where to validate. Make conversion back to the base type easy.
  Stop where the type machinery costs more than the bugs it removes; every
  pre/postcondition does not need a type.
- **Write the function you wish existed.** Mid-thought, call the function by the
  name and signature you want, finish the current idea, then implement it. The
  call fixes the abstraction before the mechanism.

## 3. One level of abstraction per body

Every line of a body sits at the same level. Stack bricks that already exist. If
you must zoom into a brick, that is a function call, not inline code.

Smells:

- a section comment inside a body ("convert name", "search", "check type");
- a raw loop over characters, bytes or indices in business logic;
- a hand-written algorithm (binary search, sort, lowercase) where the standard
  library has one;
- a process exit or panic where the caller could decide.

Method:

1. Outline what the function does, one line per step.
2. Indent each step's sub-steps (find asset: lowercase the name, search, check
   match; then check the type).
3. Group lines at the same indent into one function. Top level becomes
   "find, then check type".
4. Replace each hand-written inner brick with the library call.

A body may do real work, such as calling an algorithm and testing its result.
The line is opening the algorithm up inline.

When several methods repeat the same two-step dance (lowercase then sorted
lookup in the add path, the find path, the remove path), the manager is
maintaining an ad hoc data structure. Extract it as a type
(`CaseInsensitiveMap`) so the wrapper function disappears and callers use the
structure. This is the "missing noun" rule applied to a function body.

Name maps `{value}_by_{key}` (`assets_by_name`): it states contents and lookup key.

## 4. Counter-weights (apply judgment)

- "Extract once the code exists" is a lean, not a law. Extract when the block has
  a nameable purpose; a wrapper nobody can name fails the deletion test.
- Honesty is not worth a signature in a throwaway script or a measured hot path.
- The talk's own slide code contains bugs (never-run bounce math, a broken
  binary search, a non-compiling factory). Take the ideas, not the code.
- Not covered by the talk: error handling beyond optionals. Use the error rules
  in `SKILL.md`.
