# Servers Pattern — MCP as a Code API

Source: Anthropic, "Code execution with MCP" (2025-11-04)

## The problem it solves

Loading all MCP tool definitions upfront costs ~150k tokens before the agent reads
a single message. Every intermediate result that passes through the context window
doubles the token burn — a large document flows through twice (once as the tool
return, once as input to the next call). On financial/insurance workloads,
intermediate results often carry PII that must never enter the model.

## The pattern

Generate a `./servers/` filetree from connected MCP servers. Each tool becomes a
typed TypeScript file:

```text
servers/
├── github/
│   ├── getIssue.ts
│   ├── createPullRequest.ts
│   └── index.ts
├── linear/
│   ├── getIssue.ts
│   ├── updateIssue.ts
│   └── index.ts
├── sentry/
│   ├── getIssues.ts
│   └── index.ts
├── pagerduty/
│   ├── getIncident.ts
│   └── index.ts
└── aws/
    ├── getLogEvents.ts     # wraps read-only profile; never mutates
    ├── describeService.ts
    └── index.ts
```

Each file wraps the MCP tool call with typed input/output:

```typescript
// servers/github/getIssue.ts
import { callMCPTool } from "../../client.js";

interface GetIssueInput {
  owner: string;
  repo: string;
  number: number;
}
interface GetIssueOutput {
  title: string;
  body: string;
  state: string;
  labels: string[];
}

/** Fetch a single GitHub issue by number. */
export async function getIssue(input: GetIssueInput): Promise<GetIssueOutput> {
  return callMCPTool<GetIssueOutput>("github__get_issue", input);
}
```

The agent navigates the filesystem to discover what's available, reads only the
files it needs, and writes code that chains the calls:

```typescript
import * as github from "./servers/github";
import * as linear from "./servers/linear";
import * as pagerduty from "./servers/pagerduty";
import * as sentry from "./servers/sentry";

// Cross-system incident triage in one execution step — no context round-trips
const incident = await pagerduty.getIncident({ id: "P1A2B3C" });
const errors = await sentry.getIssues({ query: incident.title, limit: 5 });
const pr = await github.getPullRequest({
  owner: "org",
  repo: "api",
  number: 88,
});

await linear.createIssue({
  title: `[P1] ${incident.title}`,
  description: `Sentry: ${errors[0].permalink}\nPR: ${pr.html_url}`,
  priority: 1,
});
```

Token reduction: **150k → 2k (98.7%).**

## Filter in the runtime — never bloat the context

```typescript
// Wrong: 10,000 log events flow through the model
const all = await aws.getLogEvents({ logGroup: "/ecs/zyins-production" });

// Correct: filter before the model sees anything
const all = await aws.getLogEvents({
  logGroup: "/ecs/zyins-production",
  startTime: Date.now() - 5 * 60_000,
});
const errors = all.filter((e) => /ERROR|FATAL/.test(e.message));
console.log(`Found ${errors.length} errors in the last 5 min`);
console.log(errors.slice(0, 5)); // show first 5 only
```

Apply the same pattern to every high-cardinality source: GitHub PR lists, Sentry
issue queues, PagerDuty alert logs, Linear backlogs, AWS CloudWatch metrics.

## PII tokenization at the MCP-client boundary

For financial/insurance workloads, the MCP client intercepts tool responses and
replaces PII before it reaches the model:

```typescript
// What the agent sees in context:
[
  { id: "SAH-001", email: "[EMAIL_1]", ssn: "[SSN_1]", name: "[NAME_1]" },
  { id: "SAH-002", email: "[EMAIL_2]", ssn: "[SSN_2]", name: "[NAME_2]" },
];

// Real values flow from source to destination without entering the model.
// The MCP client holds the token→value map and substitutes back when a
// tokenized value appears in the next outbound tool call.
```

Use tokenization to define deterministic data-flow rules: `[EMAIL_1]` may travel
to Salesforce but not to Slack. The MCP client enforces this at the boundary before
any model reasoning can redirect it.

## Persist reusable code as skills

Once the agent develops working code for a repeating task, save it:

```typescript
// skills/tail-prod-errors.ts
import * as aws from "../servers/aws";

/** Stream the last N minutes of production ERROR/FATAL events. */
export async function tailProdErrors(minutes = 5): Promise<string[]> {
  const events = await aws.getLogEvents({
    logGroup: "/ecs/zyins-production",
    startTime: Date.now() - minutes * 60_000,
  });
  return events.filter((e) => /ERROR|FATAL/.test(e.message)).map((e) =>
    e.message
  );
}
```

Add a `SKILL.md` with YAML frontmatter so the skill is discoverable. Future agents
load the one-line stub description, then read the full file only when they need it —
progressive disclosure at the filesystem level.

## Search tool for large server sets (> 20 tools)

When the server directory grows large enough that listing all files costs tokens,
add a `search_tools` tool:

```text
search_tools({ query: "linear issue", detail: "name_and_description" })
→ [
    "linear/getIssue.ts: Fetch a Linear issue by ID",
    "linear/searchIssues.ts: Search issues by text query"
  ]
```

Detail levels: `name_only` | `name_and_description` | `full_schema`. The agent
picks the level it needs; most discovery passes use `name_only`.

## Why code execution over direct tool calls

- **Control flow is free.** Loops, conditionals, retries, and error handling run in
  the execution environment without burning model turns. A polling loop that checks
  for a deployment notification in Slack runs as a `while` loop in code — not as
  alternating tool calls and sleep commands through the agent.
- **Orchestration stays with the model.** The harness no longer decides what to do
  with every tool result; the model writes the logic. A strong coding model is also
  a strong general agent.
- **Intermediate results stay local.** Only what the code explicitly logs or returns
  enters the model's context. Sensitive data that flows from source to destination
  as a variable never touches the model.
