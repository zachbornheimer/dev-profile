---
name: execution-process
description: Use when the user says "use the execution process", runs /execution-process, or wants a dictated/incomplete request executed carefully without writing the prompt themselves.
user-invokable: true
---

# Execution Process

The user should not have to prompt-engineer. Load **prompt-writer** and run its
compile-review pipeline on their message as-is. Explicit invocation always runs;
do not skip because the ask looks small.

Then **do the work** (directly or by dispatching the compiled order). Do not return
the compiled prompt unless they asked for it, or the deliverable is itself a
prompt, skill, spec, or agent instruction.

After execution, load **verify**. Grade the resulting state against the original
intent and the order's done-when. A worker's "done" is a claim.

If the order would take an irreversible, expensive, or externally visible action,
pause for confirmation first.

`prompt-writer` compiles. This skill executes. Do not let the compiler execute.

Do not ask the user to rewrite their request.
