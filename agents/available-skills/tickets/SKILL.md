---
name: tickets
description: >-
  Create or update Linear tickets when asked — file a bug, feature, tech-debt/chore,
  improvement, or batch of issues. Reaches Linear through MCP tools or the GraphQL
  API with the local key when MCP is down. Also use when drafting issue templates,
  splitting epics into parent/sub-issues, or improving ticket quality for AI-agent
  execution. `/tickets <url-or-ID>` means rewrite an existing issue's description
  into the template — reformat, never implement, never land.
---

# Tickets

Create **actionable, self-contained Linear issues**. A world-class ticket is
executable by an AI agent, a contractor, or a senior engineer with **zero prior
context** — clear outcome, blast radius, verifiable done-when, and verify-how.

> **Linear has two doors: MCP tools, or the GraphQL API.** Prefer the tools when
> they are mounted and working. If the Linear MCP server is not connected, not
> mounted, or erroring (`MCP server not connected`, `connect` failures), do **not**
> fall back to "here is markdown, paste it yourself" — use the API below. Only a
> genuine credential absence justifies draft-for-paste.

## Linear API fallback (MCP down or absent)

The key already exists on this machine at `~/.config/linear-triage/.env` as
`LINEAR_API_KEY` (workspace SAH). Read and write through it with plain `curl`:

```bash
set -a; . ~/.config/linear-triage/.env; set +a

# read one issue (description included)
curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" -H 'Content-Type: application/json' \
  -d '{"query":"query($id:String!){issue(id:$id){identifier title state{name} description}}","variables":{"id":"SAH-123"}}'

# rewrite the description (and only the description)
curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" -H 'Content-Type: application/json' \
  -d @- <<'JSON'
{"query":"mutation($id:String!,$input:IssueUpdateInput!){issueUpdate(id:$id,input:$input){success issue{identifier updatedAt}}}",
 "variables":{"id":"SAH-123","input":{"description":"## Problem\n…"}}}
JSON
```

State ids are workspace-specific; fetch them with
`issue(id:"KEY"){ team{ states{ nodes{ id name type } } } }` and match by `type`
(`completed`, `canceled`, …). Comments: `commentCreate(input:{issueId, body})`.

Always re-read the issue after a write and report the returned `updatedAt` as the
proof — never claim a ticket changed without the read-back.

When the key is absent entirely: produce the filled markdown, name the account it
belongs to, and say the key is missing.

## Sources of truth (method)

Aligned with Linear Method + agent-execution practice:

- Write **issues, not user stories** — plain task language, not “As a developer…”
- **One outcome per issue**; scope for days, not weeks
- **Title = imperative end-state**, scannable on a board
- **Non-goals + blast radius** are mandatory (agents expand scope without them)
- **Acceptance criteria** are binary/observable; **Verify** is a runnable command list
- Architecture debt is **done** when the old path is uncallable (type/lint/test), not “cleaner”

---

## Critical: multi-account Linear (do this first)

Zach has **more than one Linear account** (at minimum: **personal** and **work/SAH**).
They are **separate workspaces**. Teams, projects, labels, and issue IDs do **not**
transfer. Filing into the wrong account is a real failure mode.

### MCP is harness-bound

Linear is reached only through whatever MCP server **this agent harness** has
connected and authenticated:

| Fact                                                                       | Implication                                                                |
| -------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Grok / Claude Code / Cursor / etc. may each wire Linear differently        | Never assume the same workspace as a previous session or another tool      |
| OAuth tokens live per MCP connection                                       | The connected server is the only workspace you can see                     |
| `linear-sah` may be enabled in one harness and disabled in another         | Absence of tools ≠ “no tickets needed” — draft for paste or switch harness |
| Server name may be `linear-sah`, `linear-personal`, plugin-qualified, etc. | Discover via tool search; don’t hardcode a server prefix                   |

**Never hardcode a team** (including `Zysys`). **Never reuse labels/projects** remembered from another workspace.

### Workspace resolution (mandatory pre-flight)

Run **before** drafting or creating any issue:

1. **Repo / work context → expected account class**

   | Path / context                               | Expected Linear class                            |
   | -------------------------------------------- | ------------------------------------------------ |
   | `~/Developer/Personal/…`                     | **Personal**                                     |
   | `~/Developer/Software-Automation-Holdings/…` | **Work / SAH**                                   |
   | Dropbox `Zysys/Software/…` legacy work trees | **Work / SAH** (confirm if mixed)                |
   | User names a project (“agentmux”, “eapp”, …) | Resolve project **after** account class is known |
   | Ambiguous / no repo                          | **Ask** which Linear account                     |

2. **Probe the connected MCP** (live discovery only)

   - `list_teams` — note team names + issue-key prefixes if shown
   - `list_projects` (query if known) — confirm the target project exists **here**
   - Issue URL host/slug if returned (`linear.app/<workspace>/…`) — record it
   - `list_issue_labels` for the team you will use — labels are **workspace-local**

3. **Match or stop**

   - If the connected workspace’s teams/projects clearly match the expected
     account class and the named project exists → proceed.
   - If the project is **missing** here but the repo is clearly personal or work →
     **stop**. Wrong account is the default explanation. Tell the user:
     - which harness/MCP identity you reached (teams you saw)
     - which account class the repo implies
     - that they must switch Linear auth / harness MCP, **or** explicitly confirm
       filing here / creating the project
   - If both accounts could fit or signal is weak → **ask once**: personal or work?

4. **Lock the filing target** for the rest of the turn
   - `account_class`: personal | work
   - `team`: discovered name/id (from `list_teams`, not memory)
   - `project`: discovered name/id
   - `label_set`: only labels that exist in this workspace
   - `issue_url_workspace`: from create response when available

Report that lock when you publish ticket IDs (“Filed in personal Linear → team X → project Y”).

### Anti-patterns (account safety)

| Bad                                                   | Good                                                       |
| ----------------------------------------------------- | ---------------------------------------------------------- |
| Default team `Zysys`                                  | `list_teams` → use what this connection returns            |
| “agentmux always goes to ZYS”                         | Find `agentmux` via `list_projects` on **this** connection |
| Reuse label list from last week                       | `list_issue_labels` on this team/workspace                 |
| Create project on the wrong account to “make it work” | Stop; fix MCP account or get explicit approval             |
| Silent file when project missing                      | Treat as account mismatch until proven otherwise           |

---

## Pre-flight (after workspace lock)

TypeSafe gate (optional, fail-open):

1. Write `{title, body, available_labels, open_titles}` to `state.json`.
2. `python3 ~/.agents/skills/typesafe-ai/scripts/typesafe.py classify-ticket --json < state.json`
3. If `source` is `typesafe`, use `issue_type`, `label`, `priority`, and `maybe_duplicate`.
4. If `source` is `fallback` or `issue_type` is `unknown`, continue with the mapping below.

5. **Project** — `list_projects` on the connected workspace; confirm name/id.
6. **Team** — from the project’s teams or `list_teams`; **never invent**.
7. **Type → label** — map to a label that **exists** in this workspace. Common
   patterns (verify live; names differ by account):

   | Type                          | Typical label names | When                               |
   | ----------------------------- | ------------------- | ---------------------------------- |
   | Feature                       | `Feature`           | New user-facing capability         |
   | Bug                           | `Bug`               | Broken / off-spec behavior         |
   | Tech debt / architecture / DX | `Improvement`       | Ownership, refactor, lint debt, DX |
   | Infra / CI / cloud            | `Cloud`             | Platform work                      |
   | Spec-only                     | `Spec`              | Design/ADR work without code yet   |

   If the workspace uses different labels (e.g. only `Bug`/`Feature`), pick the
   closest existing label or omit rather than creating labels unasked.

8. **Priority** (Linear 1–4): `1` Urgent · `2` High · `3` Medium · `4` Low · `0` none.
   Reserve Urgent for true urgency. Do not inflate.
9. **Size** — if > ~3 days or multi-package theme, **parent** + sub-issues (or a Project).
10. **Duplicates** — `list_issues` with a short query **in this workspace** first.

## Title rules

| Bad           | Good                                                               |
| ------------- | ------------------------------------------------------------------ |
| Architecture  | Close archlint capability-ownership debt and promote to fail-CI    |
| Fix heartbeat | Route heartbeat delivery through one liveness messaging capability |
| A2A cleanup   | Unify A2A wire-format codec under one protocol owner               |
| Fix the login | Login fails when email contains `+`                                |

Imperative, outcome-shaped, specific enough to scan without opening the body.

## Description templates

Pick **one** type. Fill every section; delete only if truly N/A (prefer empty bullet over missing heading).

### Tech debt / architecture (ownership, facades, lint debt)

``````markdown
## Problem

<!-- Symptom + structural cause. 2–5 sentences. Include tool/lint id if any. -->

## Goal

<!-- One sentence: invariant that becomes true. -->

## Non-goals

-
-

## Target & blast radius

- **Owner / package:**
- **Touch:** `path/…`
- **Do not touch:**
- **Callers / dependents:**

## Approach (optional, negotiable)

<!-- Preferred path; implementer may improve if invariant holds. -->

## Acceptance criteria

- [ ]
- [ ] Old path removed or uncallable (enforced by: type / lint / test — name it)
- [ ] Behavior unchanged unless explicitly listed

## Verify

```bash
# commands agent/human runs; must be pass/fail
mise run test
mise run lint
```

`````markdown
## Evidence & links

- Related:
- ADR / design / prior PR:

````text
### Bug

```markdown
## Problem
<!-- User-visible symptom in one sentence. -->

## Repro
1.

## Expected

## Actual

## Environment
- OS / build / config:

## Severity / impact

## Non-goals
-

## Acceptance criteria
- [ ] Repro no longer fails
- [ ] Regression test: `Test…` (proven RED then GREEN)
- [ ] No unrelated behavior change

## Verify
```bash
# command that failed before and passes after
````
`````
``````

## Evidence & links (bug)

- Logs / screenshots / customer quote (verbatim):

````text
### Feature

```markdown
## Context
<!-- Link project/spec; don’t restate product strategy. -->

## Deliverable
<!-- Concrete slice for *this* issue. -->

## Non-goals (v1)
-

## Target & blast radius
- **Touch:**
- **Do not touch:**

## Acceptance criteria
- [ ] Observable user/API behavior …
- [ ] Tests …

## Verify
```bash
````

## Evidence & links (feature)

- Spec / design / mock:

````text
### Ops / decision (renewal, deletion deadline, keep-or-lapse)

```markdown
## Situation
<!-- What exists, what happens if nothing is done, one or two sentences. -->

## Deadline
- **Date:** YYYY-MM-DD
- **Resets when:** <!-- the action that cancels the consequence -->

## At risk
<!-- Data, capability, or money lost if it lapses. Counts and links, not adjectives. -->

## Options
- **Keep:** <!-- action, cost, who does it -->
- **Let lapse:** <!-- what is destroyed, whether it is recoverable -->

## Resolution
- **Chosen:**
- **On:** YYYY-MM-DD by <who>
- **Evidence:** <!-- link to the confirming record; not "confirmed via Slack" -->
````

No schedule commentary, no "held for the morning pass", no deliberation narrative.

## Field mapping (Linear MCP)

Tool names vary by harness (`linear-sah__save_issue`, `mcp__linear-sah__*`, plugin
ids). Resolve via tool search. Semantic fields:

| Ticket concept | Typical parameter                                                          |
| -------------- | -------------------------------------------------------------------------- |
| Title          | `title`                                                                    |
| Body           | `description` (markdown, real newlines)                                    |
| Team           | `team` (required on create; **discovered**, not hardcoded)                 |
| Project        | `project`                                                                  |
| Labels         | `labels: [...]` (replaces full set on update — workspace-local names only) |
| Priority       | `priority`: 0–4                                                            |
| Parent         | `parentId`: issue id/identifier from **this** workspace                    |
| Blocks         | `blocks` / `blockedBy` (append-only)                                       |
| Related        | `relatedTo` (append-only)                                                  |
| Estimate       | `estimate` if team uses estimates                                          |
| Assignee       | `assignee`: `"me"` or name                                                 |

**Create:** omit `id`. **Update:** pass `id` as the identifier returned by **this** workspace.

On create failure (unknown label/project), re-list on **this** connection, fix, retry — never invent entities from another account’s memory.

## Workflow

1. **Workspace lock** (multi-account section) — stop if mismatch.
2. Pre-flight (project, team, type/label, priority, size, duplicates) on that workspace.
3. Draft title + body from the matching template.
4. **Do not ask for approval on routine filings** when the user already asked to log the work **and** the workspace lock is solid. Ask only for genuine forks: wrong/unclear account, destructive priority, huge ambiguous scope.
5. Create via the **connected** MCP; multi-part debt → parent + children; `relatedTo` among siblings when helpful.
6. Report: **account class + team + project**, identifiers, URLs, parent/child graph, suggested order.
7. Optional: project document of templates (`save_document`) **on that project’s workspace** when revising filing standards.

## Existing ticket pass — `/tickets <url-or-ID>`

`/tickets SAH-123` or `/tickets <linear-url>` means **rewrite and reformat that issue's
description**. It is an editing job on an existing ticket, not an implementation job
and not a landing job. Do not start the work, do not change state, assignee, or
priority, and do not write "done" comments. The deliverable is the same issue with a
clean, template-shaped body.

Procedure:

1. **Read the issue** — description, state, labels, comments, and any children/relations.
2. **Classify** it into one template from _Description templates_ (bug, feature, tech
   debt/architecture, ops/decision). If the body mixes motives, say so and propose a split; do not
   silently drop a motive.
3. **Extract the facts** into the template sections. Facts are dates, deadlines,
   URLs, amounts, identifiers, error text, environment, customer quotes (verbatim),
   counts, and named systems.
4. **Delete the noise** (see the table below). This is most of the work: intake
   tickets arrive wrapped in the process that produced them.
5. **Update the description** (`save_issue` / `issueUpdate` with `id` + `description`).
   Do not touch title unless it is a theme instead of an outcome — if a title change
   is warranted, make it and say so.
6. **Report** the shape of the change: which template, what was removed, what was
   promoted into which section. Never paste the whole new body back.

### Noise to strip from ticket bodies

| Noise                                                                                                                       | Why it does not belong                                                                       | Where it goes instead                                              |
| --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Personal policy, schedule, or working preference ("no work on weekends", "weekday morning pass", "do not page me before 9") | Ticket readers are the team and future agents; the owner's calendar is not ticket content    | Nowhere — it is a standing rule, already recorded outside Linear   |
| Intake provenance ("filed by the morning email-secretary pass", "mail archived in Zoho", "source: Zoho, forwarded by X")    | Explains how the row was created, not what is wrong                                          | At most a one-line `Source:` link to the original message          |
| Deliberation and hedging ("the default is to…", "unless someone objects", "very likely unused")                             | A ticket states the decision or the open question; it does not narrate the author's thinking | A decision comment, or one explicit `## Open question` line        |
| Duplicated headers/boilerplate from the source email or tool                                                                | Adds reading cost, hides the ask                                                             | Delete                                                             |
| Restated product strategy                                                                                                   | Already in the project or spec                                                               | Link it                                                            |
| "TBD", "investigate", "look into" as the whole ask                                                                          | Not an outcome                                                                               | Rewrite as the question that must be answered, with who answers it |

Keep every fact even when it sounds like noise — a date that has passed stays, as
`deadline: <date> (passed)`, because it is the record of the commitment.

---

## Decomposition

| Situation                                 | Structure                            |
| ----------------------------------------- | ------------------------------------ |
| One shippable outcome                     | Single issue                         |
| Same outcome, multiple independent slices | Parent + sub-issues (`parentId`)     |
| Hard dependency                           | `blockedBy` / `blocks`               |
| Soft context only                         | `relatedTo`                          |
| Multi-week multi-person theme             | Linear **Project**, not a mega-issue |

## Quality bar — reject / rewrite before filing

| Anti-pattern                               | Fix                                         |
| ------------------------------------------ | ------------------------------------------- |
| User-story cosplay for internal work       | Plain task language                         |
| Title = theme (“Architecture”)             | Title = concrete outcome                    |
| No non-goals                               | Agents expand scope — list exclusions       |
| No verify-how                              | “Looks done” is not done                    |
| AC as only implementation steps            | AC = observable outcomes; approach optional |
| “Clean up / improve / consider”            | Verbs with end-states                       |
| Kitchen-sink (bug + refactor + feature)    | One motive; relate the rest                 |
| Epic in one issue                          | Parent/subs or Project                      |
| Context only in Slack                      | Paste evidence + links in the issue         |
| Hardcoded team / cross-account assumptions | Live discovery + path→account class         |

An acceptance criterion that cannot be checked by a human, a test, or a command is **not** an acceptance criterion — rewrite until it is.

## Architecture / tech-debt checklist (extra)

1. Name the **missing noun/owner** (capability), not “clean up X.”
2. State the **invariant** that must become true.
3. List **call sites / packages** in blast radius.
4. Prefer **additive migration** (owner first, then callers).
5. Done = **old path hard/impossible** (lint rule, type boundary, deleted API).

## Gotchas

- **`/tickets <url>` is a rewrite, not a work order.** The ask is a clean body, not a
  fix, not a state change, not a landing. Implementing on `/tickets` is the wrong job
  done well.
- **Never put the owner's standing policy in a ticket.** Working hours, weekend
  rules, notification preferences, and personal scheduling are not ticket content —
  they read as leakage to anyone else and to the next agent.
- **Wrong Linear account** is worse than no ticket — always lock workspace first.
- **Harness MCP ≠ universal access** — personal tickets may be impossible from a work-auth harness and vice versa; draft for paste or ask to switch.
- **Labels replace the full set** on update when `labels` is passed — include all labels you want to keep; names must exist here.
- **Relations are append-only** via `blocks` / `relatedTo`; use `remove*` variants to drop.
- **Parent/child and related IDs** must be from the same workspace.
- **Icon on documents** must be a valid Linear icon name (or omit) — invalid icons 400 `save_document`.
- **Do not invent labels/teams/projects** across accounts.
- Without Linear MCP: output filled markdown + field table + **which account** to paste into; do not pretend the ticket exists.

## Example (filing discipline, not a default target)

````markdown
Workspace lock: personal (repo ~/Developer/Personal/agentmux)
teams visible: <from list_teams>
project: agentmux (from list_projects)
team: <from project.teams>
Title: Unify A2A wire-format codec under one protocol owner
Label: Improvement (verified via list_issue_labels)
Priority: Medium
Body: Problem → Goal → Non-goals → blast radius → Approach → AC → Verify → Evidence

```text
Do **not** treat any team key (e.g. `ZYS-…`) as universal — prefixes are workspace-specific.
```
````
