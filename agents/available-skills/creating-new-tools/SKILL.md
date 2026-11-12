---
name: creating-new-tools
description: >-
  Use when creating, extending, or improving a reusable agent TOOL or fixed
  WORKFLOW that an agent calls: a native omp / OhMyPie / oh-my-pi custom tool
  (a single TypeScript file in ~/.omp/agent/tools/ or a repo's .omp/tools/,
  with a workflow implemented as one tool whose execute() runs fixed steps), a
  tool in the @zab-ai/ai package (packages/ai) exposed through the Mastra MCP
  gateway as `capability run <name>` and tool_search, or both from one core
  with an omp adapter (mastra/adapters/omp/zab-ai-tools). Use for "I want to
  create a tool or extension for omp that does X", "port this Mastra workflow
  to an omp tool", and when repeated agent work suggests a new deterministic or
  AI-assisted tool. Covers where it belongs, writing descriptions that route
  through tool_search and UserPromptSubmit, typed contracts, omp custom-tool
  shape and pi.zod limits, live testing in a fresh herdr pane agent, branch
  registration for CI, kit + Mastra mount + omp adapter wiring, parity tests,
  and landing a GitHub PR. Not for a personal slash command, display toggle, or
  session hook (updating-oh-my-pi), and not for one-off scripts or work an
  existing capability covers.
---

# Creating and improving agent capabilities

## Outcome

Turn **repeatable agent work** into reliable, discoverable, typed capabilities.
A capability may orchestrate deterministic code, a validated AI prompt, multiple
model steps, external systems, or a combination. Its value is measured by better
outcomes—not by how many tools exist.

A completed capability must:

1. Solve a specific user-level job with clear boundaries and a stable contract.
2. Be selected for relevant intents, _not_ selected for adjacent or unsafe intents,
   and accept arguments agents can supply correctly.
3. Produce useful, validated results and handle failure without false success.
4. Reduce recurring errors, cost, time, or agent work compared with the baseline.
5. Be tested in the real execution environment and merged safely into `main`.

Tools registered in this system are intended for discovery via `tool_search` and
suggestion on `UserPromptSubmit`. **Registration alone does not prove either
path selects the tool correctly.** Test discovery separately from execution.

## 0. Where does it go?

Decide by **who invokes it**, before anything else.

| The request                                                                                                                              | Home                                                                                                                                                                                     | Load                   |
| ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| A tool or fixed workflow an omp agent calls ("a new tool for omp", "port this tool/workflow to omp", "move X into `~/.omp/agent/tools`") | self-contained in `~/.omp/agent/tools/<name>.ts` or `~/.omp/agent/tools/<name>/index.ts` (personal) or `.omp/tools/<name>.ts` in a repo (§4.2); zero `@zab-ai/ai` or `@mastra/*` imports | this skill (§4.2)      |
| A tool non-omp harnesses call over the MCP gateway ("expose it over MCP", "add it to zab-ai")                                            | `@zab-ai/ai` kit + Mastra mount (§4); `mastra/adapters/omp/zab-ai-tools` (§4.1) is legacy and being migrated into `~/.omp/agent/tools/`                                                  | this skill (§4)        |
| Behavior the user triggers or sees: slash command, display toggle, transcript hide, session hook                                         | self-contained extension in `~/.omp/agent/extensions/`, auto-discovered                                                                                                                  | `updating-oh-my-pi` §1 |
| A bug or feature in omp itself, or landing a branch into the custom build                                                                | topic branch on the fork, listed on `ci`                                                                                                                                                 | `updating-oh-my-pi` §2 |

"An extension to OhMyPie that does X, Y, and Z" is ambiguous. If an agent calls
X, Y, and Z, it is a tool: continue here. If the user invokes or watches them,
it is a personal extension: load `updating-oh-my-pi`. A request can be both:
build the tool here and its command there, and do not duplicate logic across them.

## 1. Decide whether to create a capability

When you encounter a recurring failure, costly sequence, repeated instruction,
or otherwise promising workflow, consider codifying it. Proactively create a
capability during authorized engineering work when it is clearly within scope
and justified by the criteria below; do not expand unrelated work merely to add
tools.

Prefer, in order:

1. **Reuse** a suitable existing capability or deterministic library function.
2. **Improve** an existing capability whose contract already covers the intent.
3. **Add a simple function or script** when tool discovery and agent invocation
   add no value.
4. **Create a capability** when a reusable agent-facing operation is warranted.

A good candidate has a recurring, recognizable intent and at least one of:

- A multi-step workflow with stable inputs and observable completion criteria.
- Repeated agent mistakes that explicit validation or deterministic code can prevent.
- Expensive, high-token, or inconsistent prompt sequences worth centralizing.
- A need for a typed result, controlled side effect, or integration with a real system.
- A clear boundary that lets agents delegate the work without remembering details.

Do **not** create one merely to wrap a single shell command, duplicate an existing
tool, codify a one-off task, or move ordinary logic behind another model call.
Prefer deterministic code over prompting for parsing, branching, validation,
formatting, and other behavior that can be specified exactly.

Before implementation, note the intended callers, example requests, the current
baseline, what improvement is expected, and why an existing tool is insufficient.
If this case is weak, fix the existing path instead.

## 2. Design for discovery: the description is a routing contract

The **name and description determine whether an agent finds and selects a tool**.
The input schema then determines whether it can call the tool correctly. Write
these _before_ implementation, and revise them against actual discovery tests.

There are three distinct description surfaces:

- **This skill's frontmatter:** when an agent should load these implementation
  instructions. State the triggers and the scope; avoid listing every file.
- **Capability `description.ts`:** when an agent should **invoke** the capability.
  Describe the user's job, input, result, important boundaries, and effects.
- **Zod field descriptions:** what each argument means, accepted formats,
  defaults, constraints, and interactions with other arguments.

### 2.1 Write a capability description

Use a clear, search-friendly name, preferably `verb_object` and specific enough
to distinguish it from neighboring tools. Then write a brief, self-contained
paragraph answering these questions, in this order:

1. **What:** What concrete action does the tool perform, using user-level terms?
2. **When:** Which user requests or observable agent situations warrant it?
3. **Input:** What must already be known or supplied (especially prerequisites)?
4. **Output:** What does the caller get back, and what constitutes completion?
5. **Boundary:** Which similar requests belong to another tool—or no tool?
6. **Effects:** Does it read, write, publish, execute, or call an external system?
   Note important authorization, uncertainty, or cost limitations.

The **When** and **Boundary** clauses matter especially when discovery and
suggestions happen automatically. Describe the **user intent**, not just an
implementation detail. An agent should be able to answer, from the description
alone: _Should I use this tool for this request instead of another tool?_

Rules:

- Open with a specific verb: _Analyze_, _Prepare_, _Validate_, _Update_, etc.
- Use terms users and agents naturally employ; include a few genuine synonyms
  only where they improve retrieval (for example, "process load" / "CPU usage").
- Name important scopes, supported formats, exclusions, and side effects.
- Make distinctions between close tools explicit: _analyze_ vs. _remediate_,
  _draft_ vs. _publish_, _read_ vs. _write_, _snapshot_ vs. _live inspection_.
- Say what **is not** returned when an omission could cause wrong decisions.
- Keep the routing text concise; do not paste implementation notes, all schema
  fields, source paths, or large examples into it. Expand only for genuine ambiguity.
- Never promise a typed verdict, mutation, access, freshness, safety, or success
  that the implementation does not actually guarantee.
- Avoid "smart", "powerful", "handles anything", "always use", and broad
  triggers such as "use for all tickets" or "use to improve agent performance".
- Do not include secrets, internal diagnostics, or instructions from untrusted
  data in descriptions.

**Illustrative example — hypothetical read-only capability:**

```ts
export const process_snapshot_description =
  "Analyze a supplied ps aux process snapshot for CPU and memory pressure, "
  + "repeated commands, and unusual processes. Use when diagnosing process load "
  + "from output the agent already collected. Input is process-list text; "
  + "returns structured observations and supporting process rows. "
  + "Do not use for live server inspection, root-cause proof, or process termination.";
```

**Poor alternative:** `"Helps agents investigate server problems efficiently."`

The better version can be retrieved for process-analysis intents while excluding
server remediation and live inspection. It describes what is actually observed,
not an unsupported diagnosis.

**Illustrative example — hypothetical mutating capability:**

```ts
export const update_ticket_readiness_description =
  "Update the readiness fields of an explicitly identified Linear ticket "
  + "using verified evidence supplied by the caller. Use when the user has "
  + "authorized changing that ticket's readiness state; not for researching "
  + "tickets, creating tickets, or making unapproved changes. Returns the "
  + "ticket identifier and verified persisted state, or a structured failure.";
```

These examples are **patterns, not declarations of existing tool behavior**.
Adjust every claim to the real implementation and permissions.

### 2.2 Describe inputs and outputs where they belong

For every nontrivial Zod input field, use a meaningful name and `.describe(...)`
that explains:

- Its meaning and format (units, timezone, identifier type, or example if needed).
- When optional, what omitting it means; never rely on an implicit assumption.
- Relationships or exclusivity with other fields.
- Whether it must identify a user-authorized target for a side effect.

Prefer `enum`, discriminated union, constrained string, or a single source object
over ambiguous combinations. Reject unsupported states early. Do not make agents
supply data the runtime can safely derive.

**Wire-schema and description budget (measured 2026-11-10/11):**

- Every character in a disclosed (top-level) tool's `description` and JSON Schema is sent on **every turn**. Compacting `run_command` in `~/.omp/agent/tools/run_command/` from 10,598 wire chars (4,515 desc + 5,999 schema) to 3,832 wire chars (1,222 desc + 2,610 schema) cut startup cost by **2,508 tokens per turn** (~10,000 tokens over a 4-turn task) while keeping a 100% pass rate.
- Never paste JSON schemas, multi-paragraph tutorials, or repeated constraint prose (`{minLength: 1}`, `{exclusiveMinimum: 0}`) into `.describe(...)`. Keep field descriptions to one short phrase (`"Max 300"`, `"Absolute; default session cwd"`), and enforce value refinements and cross-field rules per variant `type` inside `execute()` / `validateInput()` with a clear error message instead of inflating the wire JSON Schema with `oneOf` unions.
- Keep required fields explicit in `z.object({ ... })` (avoid making the primary argument `.optional()` unless `{}` is a valid call). `onUserPromptSubmit.ts` (`argsExample` and `readToolSource`) builds the `<tools>` `how-to-call` example from required fields; when a tool has no required fields (and no `command` property), its `how-to-call` shows `args: {}`, which causes agents to call `tool_call` with empty args and burn an extra turn.

For outputs, document the shape and semantics: stable IDs, observed vs. inferred
facts, warnings, partial results, and failure status. Prefer compact, structured,
high-signal results to verbose narration. Never disguise a failed operation as
an ordinary success response. Do not emit sensitive data unnecessarily.

### 2.3 Test selection, not just wording

Before writing the tool, create a small discovery fixture with realistic prompts:

- **Positive:** direct requests, paraphrases, and requests that imply the job
  without naming the tool.
- **Negative:** adjacent tasks, incomplete prerequisites, informational questions,
  and cases where the tool's effects would be unauthorized.
- **Competitive:** requests that might select an existing overlapping tool.

For each fixture, record the **expected tool or no-tool decision** and why.
Exercise the actual `tool_search` and `UserPromptSubmit` suggestion path where
available. Check both whether the correct tool is found and whether incorrect
suggestions are suppressed. Do not claim tests for a route you cannot exercise.

Run the real suggestion path and read the shortlist and `how-to-call` examples it produces:

- **In omp (primary):** `UserPromptSubmit` lives self-contained in `~/.omp/agent/extensions/onUserPromptSubmit.ts` (`discoverTools`, `discoverSkills`, `discoverMcpTools`, `retrieveShortlist`). Test discovery and `how-to-call` rendering with `cd ~/.omp/agent/extensions/hooks && bun test user_prompt_submit.test.ts`, and inspect live fire logs in `~/.local/state/omp-hooks/onUserPromptSubmit.jsonl`.
- **In Mastra (legacy gateway):**

```sh
cd ~/Developer/Personal/capability-replicas/mastra
./bin/capability run suggest_skills_tools_and_mcp --fresh --text "<prompt>" \
  | jq -r '.output.Suggestions[]? | "\(.Confidence)  \(.Name)"'
```

The suggester ranks skills by their **frontmatter `description`**, so this skill's
own description is part of the routing surface: phrase it in the words users say
("a new tool for omp", "extension for OhMyPie", "zab-ai package", "MCP gateway").

Treat unsafe false-positive selections as release blockers. Fix overlapping
names/descriptions or narrow the tool's contract rather than adding generic
"always use" instructions. Rerun the same fixtures after changing a description.

## 3. Design the execution contract

Before creating files, decide:

- Input and output Zod schemas, including invalid-input and partial-failure cases.
- What is deterministic code vs. what genuinely needs a model.
- What data is observed, inferred, or written, and how success is independently
  verified from the system of record.
- Required tools, network, permissions, timeouts, retries, and cancellation.
- Whether retries are safe; use idempotency keys or read-before-write when
  duplicate mutations could matter.
- Whether caching is valid for this operation; never cache mutable/fresh data
  without an explicit, justified policy.
- How untrusted source content is delimited and kept from acting as instructions.
- The minimal useful output: enough evidence for callers to act without dumping
  transcripts, secrets, or unrelated context.

Authorization belongs at the actual mutation boundary, not solely in a prompt
or description. Never run a live mutating smoke test on an arbitrary ticket or
resource. Use only an explicitly authorized target or a safe dedicated fixture.

## 4. Implement in `@zab-ai/ai`; mount in Mastra

A capability's logic, schemas, prompt, and description live in `@zab-ai/ai`.
Mastra supplies only the thin `defineCapability` mount. Read
`packages/ai/LAYOUT.md` and inspect the current `prepare_ticket` reference
(`packages/ai/src/tools/ticket/`, `mastra/src/capability/prepare_ticket/`),
plus nearby examples, **before copying a file layout or command**. The historical
reference was landed as `72679dfb2c`; current source and repository conventions
win if they differ.

```text
packages/ai/src/tools/<family>/
  description.ts   exported runtime selection description
  schemas.ts       Zod input/output schemas and inferred types
  <name>.ts        NAME constant and execution function
  <name>.yaml      ai-question-schema prompt, when needed (never Markdown)
  index.ts         capability.register(...) and re-exports
mastra/src/capability/<name>/<name>.ts   thin defineCapability mount
```

Update the wiring used by the current repository:

1. `packages/ai/package.json` `exports`: expose the family entry and **every
   leaf subpath the Mastra mount actually imports** (directly or via an existing
   export pattern). Verify resolution; a family-only export does not necessarily
   make `/description`, `/schemas`, or `/<name>` importable.
2. `packages/ai/src/tools/index.ts`: `import "./<family>/index.js";` in alphabetical
   order to register the package tool.
3. `mastra/src/capability/index.ts`: import the mount and register it in
   `capabilities`.
4. `mastra/test/runtime/text_input.test.ts`: add `<name>: "json"` to `FORMS` when
   applicable. Its coverage test detects registered capabilities missing here.

**Import leaf modules in the Mastra mount**, never
`@zab-ai/ai/tools` or `@zab-ai/ai/tools/<family>`: the aggregating imports
register tools as side effects. See the existing comment in
`mastra/src/capability/edit/edit.ts`.

```ts
import { runX, X_NAME } from "@zab-ai/ai/tools/<family>/<name>";
import { x_description } from "@zab-ai/ai/tools/<family>/description";
import {
  x_input_schema,
  x_output_schema,
} from "@zab-ai/ai/tools/<family>/schemas";
import { defineCapability } from "../../runtime/capability.js";

export const x = defineCapability({
  name: X_NAME,
  description: x_description,
  needs: { tools: [], network: true }, // Set from real needs, not this example.
  cache: false, // Enable only for safe, justified caching.
  input: x_input_schema,
  output: x_output_schema,
  async run(input) {
    return await runX(input);
  },
});
```

`createTool` from `@mastra/core/tools` does **not** register a
`capability run` executable. That command resolves `defineCapability` entries
in Mastra's capability index. Keep `@mastra/core` out of `@zab-ai/ai`; any
framework-specific wrapper belongs in Mastra.

### 4.1 Also a native omp tool: one core, two mounts

A kit tool reaches agents through the Mastra mount (the `mcp__capability_…`
gateway tool and `capability run <name>`). Add an **omp adapter** only when the
tool must be a first-class omp tool: it needs the omp process (session id,
`context.invokeTool`, the native job registry), or it replaces a builtin
(`edit`, `write`, `todo`, `run_command`, `wait`). Otherwise the Mastra mount
alone is the finished tool.

**One-core rule.** `@zab-ai/ai` owns every decision: description, input schema,
policy, output shape. The Mastra mount and the omp adapter only bind **ports**
(the side effects the host performs: processes, filesystem, clock, session). Both
mounts must expose the same description, schema, and output. A parity test proves
it; a copied decision in either mount is a defect.

```text
packages/ai/src/tools/<family>/ports.ts   port interfaces the host implements
packages/ai/src/tools/<family>/README.md  required for every family
packages/ai/package.json exports          "./tools/<family>" -> "./src/tools/<family>/index.ts"
packages/ai/test/tools_<family>.test.ts   kit behavior against fake ports
packages/ai/test/test_registry.test.ts    add <family> to TOOL_FAMILIES
mastra/src/capability/<family>/ports.ts   real ports for the gateway process
mastra/src/capability/<family>/<family>.ts  defineCapability mount (§4)
mastra/adapters/omp/zab-ai-tools/<name>.ts  default-export ToolFactory
mastra/adapters/omp/zab-ai-tools/index.ts   add the factory to the registration loop
mastra/test/capability/<family>_one_core.test.ts  parity: same description, schema, output
mastra/test/capability/<family>_import_boundary.test.ts  model: run_command_import_boundary.test.ts
```

Adapter shape (copy `todo.ts` for a delegating tool, `wait.ts` for one that
registers the kit's JSON Schema directly):

```ts
import { x_description } from "@zab-ai/ai/tools/<family>/description";
import { typedTool } from "./types.js";
import type { ToolFactory } from "./types.js";

const factory: ToolFactory = (pi) =>
  typedTool({
    name: "<name>", // a builtin's own name overrides it; a new name adds a tool
    label: "<Label>",
    description: x_description,
    parameters: pi.zod.object({/* same fields as the kit schema */}),
    async execute(_toolCallId, params, signal, _onUpdate, context) {
      // call the kit with the omp-process ports; context.invokeTool(params)
      // delegates to the builtin of the same name.
    },
  });
export default factory;
```

Facts that cost time when missed:

- The adapter loads inside the omp process, where `@mastra/*` does not resolve.
  Every module it reaches imports only node built-ins, `@zab-ai/ai`, and this
  repo's runtime modules; the boundary test enforces it.
- Registering under a builtin's name is last-wins. Import leaf paths from the
  kit (`@zab-ai/ai/tools/<family>/schemas`), not a family index that does not
  re-export them.
- `~/.omp/agent/extensions/zab-ai-tools` is a symlink to
  `mastra/adapters/omp/zab-ai-tools`. Interactive omp loads it ambiently after a
  restart; headless `omp -p` does not discover it (at-ty29zv), so there `edit`,
  `write`, and `todo` are the gateway's tools.
- Personal behavior no agent calls (a slash command, a display toggle, a session
  hook) is not an adapter. It is an extension in `~/.omp/agent/extensions/`; load
  `updating-oh-my-pi` §1.

### 4.2 Native omp custom tool, no Mastra (default for omp work)

A workflow is a tool. A fixed workflow is one custom tool whose `execute()` runs
ordinary functions in a fixed order; the model calls the tool, not the steps.
No `@zab-ai/ai`, no Mastra mount, no gateway.

**Where.** `~/.omp/agent/tools/<name>.ts` (or `~/.omp/agent/tools/<name>/index.ts`
when the tool has helper modules and unit tests, like `~/.omp/agent/tools/run_command/`)
for a personal tool; `.omp/tools/<name>.ts` inside a repo for a project tool.
The oh-my-pi fork builds `.omp/tools/**` and `.omp/tests/**` in CI, so put shared
repo tools there.

**Visibility: disclosed upfront vs lazy (`hidden: true`, `loadMode: "discoverable"`).**

- Only the tiny startup core (`run_command`, `write`, `read`, `tool_search`,
  `tool_call`, `skill_search` in the 6-tool `lean` benchmark config — 117.6k
  tokens/task and 33.7 s vs 752.6k tokens/task and 63.5 s with all 168 tools
  disclosed) belongs on the top-level startup tool list.
- **Every other custom tool in `~/.omp/agent/tools/` MUST set both `hidden: true`
  and `loadMode: "discoverable"`** on the object returned by the factory:
  - `hidden: true` keeps omp from sending the tool's schema on every turn (**0
    startup tokens**).
  - `loadMode: "discoverable"` is the valid `ToolLoadMode` value (`"essential" |
    "discoverable"`; `"hidden"` is **not** a valid `loadMode` and triggers an
    `audit_startup` finding).
  - `onUserPromptSubmit.ts` (`readToolSource`) and `tool_search`
    (`discoverDiskCustomTools`) still scan `~/.omp/agent/tools/<name>.ts` and
    `~/.omp/agent/tools/<name>/index.ts` on disk, surface the tool in the
    per-prompt `<tools>` XML block (with required field names extracted from
    `z.object({ ... })`) and in `tool_search` results, and `tool_call({ address:
    "omp/<name>", args })` executes the factory in-process on demand.

**Shape.** Default-export a `CustomToolFactory`, not an extension:

```ts
import type { CustomToolFactory } from "@oh-my-pi/pi-coding-agent";

const factory: CustomToolFactory = (pi) => {
  const z = pi.zod;
  return {
    name: "<name>",
    label: "<Label>",
    description: "<routing contract, §2.1>",
    hidden: true,
    loadMode: "discoverable",
    parameters: z.object({
      // Keep required fields non-optional in z.object({ ... }) so
      // onUserPromptSubmit.ts extracts them into the how-to-call example.
    }),
    async execute(_toolCallId, params, onUpdate, ctx, signal) {
      // ctx.sessionManager is the live session; pi.exec runs subprocesses.
      return {
        content: [{ type: "text", text: "<rendering>" }],
        details: output,
      };
    },
  };
};
export default factory;
```

- **Argument order differs by surface.** Custom tools: `execute(id, params,
  onUpdate, ctx, signal)`. Extensions (`pi.registerTool`):
  `execute(id, params, signal, onUpdate, ctx)`. A file that exports
  `(pi: ExtensionAPI) => pi.registerTool(...)` belongs in `extensions/`; do not
  put it in `tools/`, which expects the factory to return the tool object.
- **`pi.zod` is omp's own `omptype`, not Zod.** It has `optional()`,
  `nullable()`, `describe()`, `int()`, `positive()`, `min()`, `max()`, `enum`;
  it has **no `.nullish()`**. Write `.nullable().optional()` for a field models
  may send as `null`. Check any other Zod method against
  `packages/omptype/src/zod.ts` in the fork before using it.
- **Return `details`** as the typed output object and put the model-facing text
  in `content`. Return a typed `denied` result for refusals the caller can fix,
  throw for unexpected failures (Tool standard rule 4); never return a failure
  as success.
- **No MCP time limit.** `execute()` has none, so a long workflow is fine if it
  sends `onUpdate` heartbeats (see `~/.omp/agent/tools/ask_mastra.ts`), passes
  `signal` to `pi.exec` and every await, and clears its timers in `finally`.
- **Self-contained.** Zero imports from `@zab-ai/ai`, `@mastra/*`, or
  `capability-replicas`. Put helper modules and unit tests inside
  `~/.omp/agent/tools/<name>/` (with `index.ts` as the entry point).

**Tool standard (same bar as the extension standard).** The exemplar for extension shape is `~/.omp/agent/extensions/onUserPromptSubmit.ts` (see `updating-oh-my-pi` `references/extensions.md`, "Extension standard"); the exemplar for a tool is `~/.omp/agent/tools/run_command/`. A new tool MUST:

1. Open with a header comment stating its one responsibility and naming where each other concern lives.
2. Keep `index.ts` a thin factory: name, description, schema, and an `execute()` that validates, calls the pure core, and renders. Decisions, parsing, and policy live in sibling modules with no omp imports.
3. Put per-variant and cross-field validation in a `validateInput`-style function with a clear error, not in an inflated wire schema (§2.2 budget).
4. Report failure truthfully, in one of two ways. A refusal the caller can act on (bad input, policy, scope) is a typed result: `details: { status: "denied", reason }` with the same text in `content`, as `run_command` does through `denied()`. An unexpected failure (bug, I/O error, abort via `signal?.throwIfAborted()`) throws. Never return a failure as success, and put non-fatal problems in the result instead of swallowing them.
5. Take every side effect (process, filesystem, clock, network) through a parameter or port so tests can fake it.
6. Ship `*.test.ts` files beside the pure modules in `tools/<name>/`, covering behavior, boundaries and errors; run them with `bun test`.
7. Be hidden and discoverable unless it belongs in the startup core, with a routing description (§2.1) and required fields non-optional.
8. Stay self-contained (no `@zab-ai/*`, `@mastra/*`, or `capability-replicas`) and never mutate host objects it did not create.

**Workflow steps.** Keep steps as plain functions in the same module (or sibling
files in `~/.omp/agent/tools/<name>/`), called in order by `execute()`. For a
judgment step, spawn `omp -p` or `--mode rpc` with a schema through `pi.exec`,
as `work_ticket_with_omp` does. There is no suspend and resume: record each
step's result (an `atask` log or a JSON state file) so a rerun skips finished
steps, and say in the description when a run is not resumable.

**Loading and `tool_call` execution gotchas.**

- Top-level tool files load at session start; restart (or `omp_restart`) to pick
  up top-level schema changes. Load failures are silent in the session and
  logged as `Custom tool load failed` in `~/.omp/logs/omp.<date>.<pid>.log`.
- When invoked lazily via `tool_call({ address: "omp/<name>", args })`,
  `executeCustomTool` dynamically imports `~/.omp/agent/tools/<name>.ts` (or
  `<name>/index.ts`). A newly created file in `~/.omp/agent/tools/` is callable
  immediately via `tool_call` in a running session, **but** Bun caches the ES
  module by file URL per process—subsequent edits to that file will not take
  effect inside `tool_call` until the omp session restarts.
- While `extensions/zab-ai-tools` remains installed, its `host.hosted` map takes
  precedence over `~/.omp/agent/tools/<name>` inside `tool_call({ address:
  "omp/<name>" })` (even though `~/.omp/agent/tools/<name>` wins for direct
  top-level calls). And any omp builtin or extension tool that is hidden from
  the top-level allowlist without a corresponding entry in `~/.omp/agent/tools/`
  or `host.hosted` fails inside `tool_call` with `omp hosts the tool "<name>"
  itself and tool_call cannot run it`.

## 5. Write and validate model prompts only when needed

Prompts are **ai-question-schema YAML**; load the `ai-question-schema` skill
before editing one. Validate with:

```sh
python3 ~/.agents/skills/ai-question-schema/scripts/validate_question_file.py \
  packages/ai/src/tools/<family>/<name>.yaml
```

Supply interpolation values using `loadQuestionFile` and
`promptTextOf(file, state)` from `packages/ai/src/questions.ts`. When a prompt
needs text from a skill or document, read it in the run function and inject
it as state (for example, `{tickets_skill}`). `$(cat ...)` is not evaluated
inside YAML.

A prompt should specify the job, necessary context, trustworthy data boundaries,
output contract, stop/ambiguity behavior, and evidence requirements. Prefer a
small number of representative examples only when they correct observed errors.
Do not demand verbose intermediate reasoning or ask a model to perform arithmetic,
parsing, validation, or retries that code can do more reliably.

## 6. Run tool-using agents through the full OMP environment

When the capability needs an agent with Linear, shell, filesystem, MCP, or other
real tools, use a full OMP process: `omp -p @<promptfile>` **without `--agent`**.
Write the prompt to a private temporary directory with `mkdtemp`/`writeFile`,
spawn `omp` with argument-array APIs (not shell interpolation), capture stdout
and stderr, check process exit status, enforce an appropriate timeout, and remove
the temporary directory in `finally`. Avoid leaking credentials or prompt
contents in logs. Confirm the actual required tools were available in a real run.

Do **not** use `thread()` / `ompSdkSessions()` for work that needs those tools:
`omp-session.ts` (`ompTurnOptions`) creates sessions with
`toolNames: ["yield"]`, plus anything the host separately adds. In a previous
`ZYS-5542` run, the agent could not access Linear and changed nothing. Thread
sessions are appropriate for transcript-reading workloads such as the learn
family, not for unverified external actions.

A full OMP session may return **free text**, despite a schema in the question
file. Treat the transcript as evidence of an attempt, not as a typed or verified
result. When an operation changes Linear or another system, re-fetch the actual
record and construct the typed result from persisted state. If structured output
is essential and cannot be independently obtained, design an enforceable output
channel or fail explicitly; do not regex a guessed verdict out of prose.

## 7. Verify behavior before submitting a PR

Run the smallest relevant checks, then the integration and selection tests:

1. **Prompt:** Validate YAML if a question file exists.
2. **Resolution + validation:** From `mastra/`, run
   `./bin/capability run <name> --input 'null'` for an object-input
   capability (or another **syntactically valid JSON** value the input schema
   rejects). Verify that the command resolves the correct tool and returns
   `invalid input for <name>: ...`, rather than an unknown-tool or JSON parser
   error. `{}` is only a useful probe when the schema requires fields.
3. **Registry:** `cd mastra && bun test test/runtime/text_input.test.ts`.
4. **Code:** Run focused unit/integration tests and the repository's relevant
   typecheck/lint commands. Use `bun test <file>`; this repository blocks
   Vitest through its pinned `test` script. Follow existing `bunx` / `mise run`
   conventions; do not substitute `npm`/`npx`.
5. **Real execution:** At least one end-to-end run with an authorized target
   or safe fixture. Check output schema, actual tool access, error handling,
   and independent observation of any side effect.
6. **Discovery:** Rerun the positive, negative, and overlapping-intent fixtures
   from §2.3 against the actual search and suggestion paths, and record the
   confidence the suggester gave the right skill or tool.
7. **Native omp adapter only (§4.1):** the registry, parity, and import-boundary
   tests pass, and a live interactive omp run (herdr pane, `/force:<tool>`)
   shows the native tool called and its result rendered. A headless `omp -p`
   run does not prove it: ambient extensions are not loaded there.
8. **Custom tool (§4.2):** all three, in this order.
   1. **Load it against omp's own `pi.zod`**, not Zod: import
      `packages/omptype/src/zod.ts` from the fork, call the factory with
      `{ zod }`, and run `parameters` on a valid input, a `null` optional, and
      an invalid value. Real Zod accepts methods omptype lacks, which is how a
      `.nullish()` shipped.
   2. **Run it in a fresh herdr pane agent** started after the file was final
      (`herdr pane split --current --direction right --cwd "$PWD" --no-focus`,
      `herdr agent start <name> --kind omp --pane <id>`, `herdr agent prompt`).
      Tell the agent the exact tool name and forbid `tool_call` and
      `capability/*`, otherwise it silently uses the Mastra twin. If the prompt
      sits unsent, `herdr agent send-keys <name> enter`. Read the pane with
      `herdr pane read <id> --source recent-unwrapped --lines 120`. If the tool
      is missing, read the omp log for `Custom tool load failed`. Close the
      pane you opened.
   3. **Diff against the Mastra output** on the same input when porting
      (`capability run <name>`), and explain every difference.
      Unit tests are `bun test` with `bun:test` in `.omp/tests/`; never Vitest.

For failure paths, test missing/invalid inputs, tool unavailability, timeout,
permission denial, upstream errors, and attempted duplicate execution where
relevant. Fail explicitly instead of silently returning an empty success.

If tests fail, distinguish regressions from pre-existing failures by running the
same check against an isolated clean baseline. Avoid risky stash/pop operations
when a separate clean worktree can establish the baseline more safely. Do not
claim a test passed if it was skipped, unavailable, or run in a different setup.

## 8. Worktrees, commits, PR, and safe landing

1. Start in **one dedicated worktree** using the repository's `wt` workflow,
   e.g. `wt switch -c <branch>` or `wt tree-for-changes <branch>`. Check the
   resulting path and branch before editing. In the `main` checkout, separate
   write calls may auto-fork worktrees; parallel writes previously produced six
   unwanted branches. Work in one worktree, and serialize conflicting edits.
2. Re-read files before retrying failed edits; parallel edits to the same file
   can race or lose anchors. Remove confirmed stray worktrees only when safe,
   e.g. `wt remove -f -D --foreground <branch>`.
3. Review the diff, run checks, and commit with
   `git commit -S -m "type: concise subject"`. Hooks require a conventional
   subject at most 60 characters; use no trailers. `wt step commit` does not
   accept `-m`.
4. Push the branch and open a **GitHub PR** using the repository's established
   workflow. Include purpose, discovery boundaries, example inputs/outputs,
   tests, and any remaining risk. Ensure required CI and reviews pass. If CI
   turns red, inspect the failure and use the repository's **Red CI fixing
   capability** if available and applicable; verify its actual name/interface
   rather than assuming one. Rerun affected checks after each fix.
5. Merge through GitHub after requirements pass. Bring the local `main` up to
   date safely (prefer fast-forward-only sync), verify the final commit and
   capability registration are on `main`, then clean up the worktree/branch
   according to repository conventions. **Opening a PR is not completion.**

The historical `wt merge -y main` workflow locally squashes/rebases/merges and
is **not** the default when GitHub PR integration is required. Use it only if the
current repository workflow explicitly calls for local landing instead. If
rebasing after `main` advances, preserve imports from both sides of
`packages/ai/src/tools/index.ts`, resolve and stage conflicts, continue the
rebase, and rerun verification. Never overwrite another tool's registration.

### 8.1 Landing a native tool branch in the oh-my-pi fork

One branch per tool, named `tools/<name>`. The fork's default branch is `ci`;
`main` is a read-only mirror of upstream and is never pushed. The branches CI
assembles into the custom omp build are listed, with a reason each, in the
`BRANCH_MANIFEST` JSON array in `.github/workflows/omp-build.yml` on `ci`.

1. Push the tool branch to the `fork` remote first, never `origin`. A listed
   branch that is missing from `fork` fails the whole assembly, and the command
   refuses to add one.
2. From a checkout of `ci`, register it with the command, not by hand:

```sh
bun scripts/omp-build/branches.ts add tools/<name> --reason "<why this branch is built>"
bun scripts/omp-build/branches.ts check
bun scripts/omp-build/branches.ts list
```

`add` appends one `{branch, reason}` entry at the end (entries merge in listed
order), editing only the lines it needs. Commit it signed with a conventional
subject and push `ci` to `fork`.

## Definition of done

Before reporting completion, verify all of the following:

- The new tool serves a documented, nonduplicative recurring intent.
- The description accurately defines use, non-use, inputs, outputs, and effects;
  similar-tool boundaries are clear.
- The registry, package exports, leaf imports, Mastra mount, and form map agree.
- Schemas reject invalid states; errors, retries, permissions, and side effects
  follow the declared contract.
- Real execution succeeded and any reported state change was independently
  verified. Discovery tests cover both selection and non-selection.
- A native custom tool loads under omp's own `pi.zod`, was called from a fresh
  pane agent that could not fall back to a Mastra twin, and its branch is
  registered with `branches.ts add` on `ci` and pushed to `fork` (§4.2, §7.8, §8.1).
- PR merged, required CI green, and the implementation is confirmed on `main`.

Report the merged PR/commit, capability name, meaningful tests performed,
observed behavior, and any unverified caveat. If blocked, state the exact
blocker and what remains; never equate a passing static check with live access.

## Reference guidance

- [OpenAI: function calling best practices](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI: tool search and deferred descriptions](https://developers.openai.com/api/docs/guides/tools-tool-search)
- [Anthropic: defining tools and descriptions](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
- [Agent Skills specification: frontmatter and progressive disclosure](https://agentskills.io/specification)
