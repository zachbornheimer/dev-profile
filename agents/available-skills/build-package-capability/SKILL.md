---
name: build-package-capability
description: "Use when adding a new tool to capability-replicas: code that lives in @zab-ai/ai (packages/ai) and is mounted in mastra so `capability run <name>` reaches it. Covers the file layout, the leaf-module mount, the registry and test-map entries, how to run an agent prompt in the user's full omp setup, how to verify, and the traps that cost time (thread sessions have no tools, parallel writes fork worktrees, commit and test rules)."
---

# Build a package capability

A tool's logic, schemas, description and prompt live in `@zab-ai/ai`. Mastra only mounts them. Reference implementation: `prepare_ticket` (`packages/ai/src/tools/ticket/` + `mastra/src/capability/prepare_ticket/`, landed on main as 72679dfb2c). Copy its shape, then read `packages/ai/LAYOUT.md`.

## Layout

```text
packages/ai/src/tools/<family>/
  description.ts   exported string: what it does, the call shape, what it returns
  schemas.ts       zod input and output schemas (+ inferred types)
  <name>.ts        NAME constant + run function (the real work)
  <name>.yaml      the prompt, as an ai-question-schema file (never markdown)
  index.ts         capability.register({...}) + re-exports of the above
mastra/src/capability/<name>/<name>.ts   thin defineCapability mount
```

Wire-ups, each one line:

- `packages/ai/package.json` `exports`: `"./tools/<family>": "./src/tools/<family>/index.ts"`.
- `packages/ai/src/tools/index.ts`: `import "./<family>/index.js";` (alphabetical).
- `mastra/src/capability/index.ts`: import the mount and add it to the `capabilities` list.
- `mastra/test/runtime/text_input.test.ts`: add `<name>: "json"` to `FORMS`. A test fails when a registered capability is missing there.

## The mount

Import the package's leaf modules, never `@zab-ai/ai/tools` or `@zab-ai/ai/tools/<family>`. Those register the tool on the package registry as an import side effect. See `mastra/src/capability/edit/edit.ts` for the comment and `prepare_ticket.ts` for a short mount:

```ts
import { x_description } from "@zab-ai/ai/tools/<family>/description";
import { X_NAME, runX } from "@zab-ai/ai/tools/<family>/<name>";
import { x_input_schema, x_output_schema } from "@zab-ai/ai/tools/<family>/schemas";
import { defineCapability } from "../../runtime/capability.js";

export const x = defineCapability({
  name: X_NAME, description: x_description,
  needs: { tools: [], network: true }, cache: false,
  input: x_input_schema, output: x_output_schema,
  async run(input) { return await runX(input); },
});
```

`createTool` from `@mastra/core/tools` is NOT what makes `capability run` work. `capability run` resolves `defineCapability` entries in `capability/index.ts`. `@zab-ai/ai` has no `@mastra/core` dependency, so any `createTool` wrapper must stay in mastra.

## Prompts

Prompts are ai-question-schema YAML (skill: `ai-question-schema`; validate with `python3 ~/.agents/skills/ai-question-schema/scripts/validate_question_file.py <file>`). Fill placeholders with `loadQuestionFile` + `promptTextOf(file, state)` from `packages/ai/src/questions.ts`. Skill or doc text that a prompt needs is read by the run function and passed in as state (for example `{tickets_skill}`); `$(cat ...)` does not work inside YAML.

## Running an agent: use a full omp session

If the tool needs an agent that touches Linear, files, a shell or MCP, run it as `omp -p @<promptfile>` with no `--agent`, from a temp file (`mkdtemp`, `writeFile`, `spawn("omp", ["-p", "@file"])`, read stdout, remove the directory). That loads the user's whole setup, including the capability gateway and MCP servers.

Do not use `thread()` / `ompSdkSessions()` for this. `omp-session.ts` (`ompTurnOptions`) creates sessions with `toolNames: ["yield"]`: the agent can call only `yield`, plus whatever the host adds. Verified on ZYS-5542: the agent reported it had no Linear access and changed nothing. `thread()` is right only for transcript-reading agents (the learn family).

The cost: output is free text. The question file supplies the prompt, but nothing enforces its schema. If a typed verdict matters, read it back from the real system (re-fetch the ticket) rather than trusting the text.

## Verify

1. Validate the question file (command above).
2. `cd mastra && ./bin/capability run <name> --input '{}'` should fail with `invalid input for <name>: ...`. That proves the name resolves and the schema is bound, without paying for a real run.
3. `bun test test/runtime/text_input.test.ts` from `mastra/`.
4. One real run against a real input before calling it done. A static check cannot show whether the agent had its tools.

## Traps

- **Parallel writes fork worktrees.** In the `main` checkout, each `write` auto-forks into its own new worktree. Six parallel writes made six worktrees. Work in one worktree from the start (`wt switch -c <branch>`, or `wt tree-for-changes <branch>`), or write files one at a time. Clean up strays with `wt remove -f -D --foreground <branch>`.
- **Edits that run in parallel on one file race.** Re-read and retry when one reports a missing anchor.
- **Tests: `bun test`, not vitest.** The repo's `test` script is pinned to vitest, and a rule blocks that. Use `bun test <file>` and `bunx` / `mise run`, never `npm`/`npx`.
- **Commits:** `wt step commit` takes no `-m`. Use `git commit -S -m "..."`. The hook requires a conventional subject of at most 60 characters. No trailers.
- **Landing:** `wt merge -y main` from the worktree squashes, rebases and merges. If main moved, the rebase can conflict on `packages/ai/src/tools/index.ts` (the import list). Keep both sides' imports, `git add`, `GIT_EDITOR=true git rebase --continue`, re-run the checks, then `wt merge -y main` again.
- **A failing test may be older than your change.** Stash, run, pop to check. In this work the form-map failure was a missing `relay_ticket` entry that main later fixed.
- **Do not add a tool to the root index.** `packages/ai/src/index.ts` deliberately does not re-export `tools`.
- **Run real tools only on a ticket the user named.** The intake run wrote to a live Linear ticket.
