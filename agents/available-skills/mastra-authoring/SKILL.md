---
name: mastra-authoring
description: "Use when a pipeline, sequence, or process is repeatable and likely to be repeated: write it as a Mastra workflow or tool. If the whole job is not repeatable, use this when any part of it is, and codify that part. Also use when writing, reviewing, or planning a Mastra workflow, tool, or agent, including a scheduled run, an MCP-exposed tool, or a batch of judgment questions. Also use when Mastra code nests checks inside checks, treats every tool as deterministic, hides missing-input calls, puts prompts in the TypeScript file, or lets a model pick the next step of a path that can be drawn. A tool is a narrow self-contained call that may judge. A workflow is a complete state change. Missing inputs are filled by declared tools only, in parallel, with no cycles."
---

# Mastra authoring

This is the shape for Mastra code that will be run the same way every time, including on a schedule, and exposed over MCP so another agent can call it. The `mastra` skill owns current APIs. This skill owns the shape. Load `mastra` and confirm signatures against installed docs before writing a call. Do not copy an API from memory or from this file.

## The call

Write a Mastra workflow or tool when a pipeline, sequence, or process is repeatable and likely to be repeated. If the whole job is not, codify the part that is. An agent owns only the part you cannot name before the run.

A workflow is a complete change from one state to another. Write one when you can name that change before the run. An agent owns the path only when you cannot.

A tool is narrower. An agent can call it at any point, including mid-conversation, in a context the workflow author did not draw. It is input, a transform or a judgment, and a typed output. It is not defined as deterministic. Some tools are judgment calls.

Most tools can be tiny workflows. That is allowed when the tool file itself shows input, transform, and output. What is banned is a check whose only job is to call another check.

Ticket organization, a dependency upgrade, and a page audit are workflows. The model answers questions inside a tool. It does not pick the next step of a path you already drew.

## Names

Name the tool for what it returns, in a form an outside agent can call.

```text
get_webpage_as_markdown
seo.identify.title
seo.identify.heading_structure
seo.assemble_facts
```

The description says what the caller gets back and when to call it. Not how the insides work. That description is what Claude Code, Codex, and other agents read over MCP.

## Safe to run

A tool does not assume the caller already fetched its inputs.

If a declared input is missing, the tool runs the tool that produces it. Independent missing inputs run in parallel. A tool may call only the tools it declares as inputs. It may not call itself, and it may not call a tool that calls it.

`seo.assemble_facts` confirms it has the facts. If title or heading facts are missing, it runs `seo.identify.title` and `seo.identify.heading_structure` in parallel. If those lack markdown, they run `get_webpage_as_markdown`. The caller can still pass w
the facts in. The tool must not fail only because the caller did not.

A failed check returns a typed failure. A throw fails a whole `.parallel()` block.

## The file is the flowchart

A workflow file names every tool and the order. A reader adds a part by adding one tool and one line. A reader changes a part by editing that tool.

```text
headingSense
  .parallel([seo.identify.title, seo.identify.heading_structure])
  .then(seo.assemble_facts)
```

`get_webpage_as_markdown` is not a required first step in that file. Each identify tool runs it when markdown is missing. Putting the fetch in the workflow is allowed when the workflow is the caller. It is not required for the tools to be safe to run alone.

Inside a tool that asks the model, the line is straight:

```text
input
  -> query the model once
  -> return the answers
```

The query is a database query against an LLM or a decision model. It returns answers, not a verdict. Assemble returns the facts. Do not add a verdict step unless a later tool is explicitly a verdict tool.

## Depth

Two levels in the file the reader opens.

1. The workflow file names every tool in the transformation.
2. Each tool file shows input, the one transform or the one query, and the output. It may call one pure helper in the same file.

A nested workflow is only for a `.foreach()` item that is itself a pipeline you would run alone. A list of checks is not that pipeline.

Calling a declared input tool is not that nesting. The call is one visible line, the declared name, not a helper chain.

Wrong: `evaluateSeo` calls `checkTitle`, which calls `titleLength`, which calls `titleWords`.

Right: `seo.identify.title` is one tool. Length, words, and sense are questions in its sibling yaml, asked in one call.

## Questions

A tool that asks the model has a sibling yaml with the same basename. Not a `questions/` folder. Not a prompt string in the TypeScript file.

The question file contract, and the validator that checks it, live in `ai-question-schema`. Do not invent a second shape. Run that skill's validator before treating the file as valid.

Ask every question for that tool in one call per model. `criteria` questions go to System One together. `schema` questions go to the LLM with the schema attached. Do not send a schema question through `.classifier()`, and do not send a criteria question to the LLM. A tool that returns answers does not need `.branch()`. Ask, then return the typed answers.

## Agents

An agent is for an open-ended task whose next move cannot be drawn. It is not the owner of a known sequence.

An agent may sit inside one tool when that tool's own path is unknown. It does not choose which tools run.

## Schedule

A scheduled run is the same workflow. Put a `schedule` field on the workflow. A manual run and a cron run share one path. Built-in cron does not fire on a serverless host that shuts down between requests. Say so when the host is serverless. Do not add a second code path for the clock.

## Local dev surface

- Serve a checkout with `mise run dev`; `mise run dev:status` prints its state read-only.
- Serving is portless: the route is a `.localhost` host, not a port. The main checkout serves `https://capability-replicas.localhost`; a worktree serves `https://capability-replicas-<slug>.localhost`. Do not hunt for port numbers.
- A run is watchable on the Studio route at `/workflows/<id>/graph/<runId>`.

## Before you write

1. Load the `mastra` skill. Confirm the signatures against installed docs.
2. Name the complete change, then name each tool for what it returns.
3. Declare which tools each tool may call when an input is missing. Reject a cycle.
4. One file per tool. One sibling yaml if that tool asks questions. The description must be good enough to expose over MCP.
5. Wire the tools in the workflow file. That file must read as the flowchart without opening the tool files.

## Done when

- Opening the workflow file shows the complete change and the order.
- Each tool can be called alone. Missing declared inputs are filled by those tools, in parallel, with no cycle.
- Adding a tool is one new file, one yaml if it asks, and one line in the graph.
- No tool file's only job is to call another check.
- No prompt or question text lives in a TypeScript file.
- A model call returns answers. Assemble returns facts. A verdict exists only in a tool named as a verdict.
- The model is not asked to pick the next step of a path you already drew.

## What this skill does not own

- Current Mastra signatures, Studio, and migrations: the `mastra` skill.
- Ownership, visible phases, and tests: `code-construction`.
- Names that say what, not how: `code-style`.
