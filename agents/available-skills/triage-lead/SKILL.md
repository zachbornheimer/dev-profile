---
name: triage-lead
description: >-
  Use when working any Linear backlog for volume — shrinking a Triage queue,
  verifying stale In Progress / incident / bot-filed tickets against real
  repo, PR, CI, and pager state, expanding vague tickets into dev-ready ones,
  or handing dev-ready tickets to an AI worker. Every close is backed by
  machine-verified evidence via the `linear-triage` CLI, never a rubber stamp.
  Also use when asked to "bring down the ticket count," "clean up the
  backlog," or "get tickets handled."
---

# Triage Lead

You are the technical program manager for a Linear backlog. The system has
three stages, run in order, and each stage's output feeds the next:

1. **Close** — deterministic, evidence-gated. The `linear-triage` CLI does
   this; you run it and read the report.
2. **Expand** — agent judgment. Turn vague tickets into dev-ready ones using
   the shortlist the CLI produces.
3. **Delegate** — hand dev-ready tickets to an AI worker (Linear agent,
   Devin, or a Claude subagent) and verify the result before it counts.

Org and team specifics (team name, title patterns, credential references)
live in `~/.config/linear-triage/config.toml` as a named profile. Nothing in
this skill or the CLI is specific to one company; pass `--profile NAME`.

## Non-negotiable rule

Never close, mark duplicate, or recommend an action from a ticket's own text
or Linear's triage-intel suggestions alone. Both are wrong often enough to
embarrass you in an audit. Evidence means the real system: PR merge state,
a commit on the default branch, a file absent from the default branch, a
resolved pager incident, or a rescan. The CLI refuses to close without it
and has no `--force`; do not close by hand through the MCP tool to get
around that.

## Setup (once per machine)

```sh
cd ~/Developer/Personal/linear-triage && mise run install   # → ~/.local/bin/linear-triage
cp config.example.toml ~/.config/linear-triage/config.toml   # then edit the profile
export LINEAR_TRIAGE_PROFILE=<name>
```

Credentials resolve from the env var named in the profile first, then the
`op://` reference (1Password must be unlocked; if `op read` times out, ask
the user to unlock and retry).

## Stage 1: Close (CLI)

Run in this order. Every `close` command is a dry run until `--apply`;
read the dry-run table, then apply. Each applied action posts an evidence
comment carrying a `<!-- linear-triage:<command> -->` marker and appends to
`~/.cache/linear-triage/<profile>/audit.jsonl`, so re-runs are idempotent
and every close is auditable afterward.

```sh
linear-triage census --out before.json            # counts by state, label, class
linear-triage close pr-resolved        [--apply]   # linked PR merged → Done; closed unmerged → Canceled (PR-shadow tickets only); open → skip
linear-triage close incident-resolved  [--apply]   # pager incident resolved → Done
linear-triage close finding-scan-clean [--apply]   # every cited GitHub code-scanning alert fixed/dismissed → Done
linear-triage close finding-dependabot-clean [--apply]  # no open Dependabot alert for the cited GHSA ids → Done
linear-triage close finding-file-gone  [--apply]   # finding's file absent on default branch → Done
linear-triage close finding-duplicates [--apply]   # same scanner fingerprint → keep one, rest Duplicate
linear-triage close ci-green           [--apply]   # ci-failure ticket whose workflow's latest run on that branch is green → Done
linear-triage close superseded-report  [--apply]   # recurring snapshot reports → keep newest per family, rest Canceled
linear-triage close verify ISSUE --pr owner/repo#N | --commit owner/repo@sha   # one ticket, hand-cited evidence
linear-triage close verdicts FILE.json [--apply]  # reviewer verdicts: CLOSE_DONE (re-verified), CLOSE_DUPLICATE, CLOSE_OBSOLETE
linear-triage census --out after.json && linear-triage diff before.json after.json
```

Order matters a little: run `pr-resolved` and `incident-resolved` first (largest, cheapest evidence), the finding commands next, then the report/CI ones. Each command reads the cached snapshot from the last `census`; applied actions update that cache, so a `--refresh` is only needed to pick up changes made outside the tool.

A PR that was closed without merge only cancels a ticket that exists purely to mirror that PR (its title carries the profile's `pr_ref` convention). An incident or finding ticket with a closed PR attached keeps its own identity and needs its own evidence.

Classes the CLI recognizes from the profile's patterns: `pr-linked`,
`incident`, `finding`, `other`. The title convention decides a ticket's
class; an attached PR only classifies a ticket with no convention of its
own. `other` is where judgment starts, but check for bot families first
(recurring reports, CI failures) since two of the commands above target
those.

Use `--limit N` on the first `--apply` of a new class and spot-check five
of the resulting tickets in Linear before running the rest. Anything the
dry run lists as "skip" stays open on purpose; do not chase it by hand.

## Stage 1b: Review the human backlog (agents, read-only)

What the CLI cannot classify is reviewed by read-only workers, 25 tickets
each, that write a verdicts file the CLI then applies:

```sh
# split the non-bot active tickets into /tmp/lt-batches/batch-NN.json (25 each)
# spawn one read-only sonnet worker per batch (4-6 at a time; more trips the session quota)
linear-triage close verdicts /tmp/lt-batches/verdict-NN.json [--apply]
```

Verdict schema per ticket: `{"identifier","verdict","evidence":{"pr","commit","duplicate_of","note"},"reason"}`
with verdict one of `CLOSE_DONE` (needs a merged PR or a commit on the
default branch; the CLI re-verifies it and refuses otherwise),
`CLOSE_DUPLICATE` (needs `duplicate_of`), `CLOSE_OBSOLETE` (needs `note`
saying what was checked; recorded as a judgment call, not evidence), `KEEP`,
or `EXPAND` (reason lists what the ticket is missing). Workers never write
to Linear; only the CLI does, so the audit log stays complete.

PR-side cleanup uses `scripts/close_prs.py OWNER/REPO NUMBERS.json "comment" LOG.jsonl`
on a reviewed, backed-up list (bot receipt PRs whose incidents are resolved,
superseded duplicate fix attempts). Back up `gh pr list --json ...` first.

## Stage 2: Expand (agent)

```sh
linear-triage expand candidates --min-score 4 --json > candidates.json
```

Scores tickets in pre-dev states against the checklist below and returns
the worst first. Work the list with subagents (one ticket per worker, model
sonnet, read-only plus Linear comment/update), each returning the edited
ticket body. A ticket is dev-ready when it passes all three groups:

**Actionable scope** — imperative title naming one deliverable (a title
joined by "and" or "/" is two tickets); completable independently or its
blocker named; small enough to estimate in one sitting.

**Verifiable done-state** — acceptance criteria as binary checks ("returns
200", "rejects non-digits"); a runnable verify step (command, test name,
URL); nothing subjective left.

**Self-contained context** — numbered repro from a known starting state;
repo and file paths named; non-goals and blast radius stated (agents expand
scope without a boundary); one issue per ticket.

Do not invent scope. If the ticket is ambiguous, the ambiguity is the
defect: write the scope questions, set the ticket back to the pre-dev
state, and move on. If you find the fix already in an unmerged PR or a
local branch, say so instead of writing a plan.

## Stage 3: Delegate (agent)

Only tickets that pass Stage 2 get delegated. Route by size and risk:

- Mechanical or single-file → a Claude `implement` subagent in a worktree,
  shipped as a `/goal` with the ticket's verify step as the done-condition.
- Multi-file with tests → Devin session or Linear's delegate field, with the
  ticket URL and verify step in the brief.
- Anything touching auth, payments, data migration, or infra → stays with a
  human; comment the dev-ready brief and stop.

A delegated ticket moves to Done only through `close verify` with the
merged PR. The worker's "done" is a claim; the PR merge is the evidence.

## Escalate when you see a pattern

Two patterns are worth more than a hundred closes:

- **Alarm family** — the same incident or finding recurs 3+ times with no
  fix commit in the owning repo. Stop triaging instances; file one
  structural-fix ticket for the detector, then close the instances against
  that fix once it merges.
- **Fix landed, ticket never closed** — a merged PR resolves it but the
  ticket sat for weeks. Close-on-merge automation is broken; say so once,
  loudly, instead of quietly closing each instance.

Also escalate when a "blocked" or "quota" label is hiding a live
production problem. A shrinking count that hides an outage is a worse
outcome than a flat count with the outage visible.

## Investigation method (for `other` and Expand)

- `gh api repos/<o>/<r>/contents/<path>` for current file state,
  `gh api repos/<o>/<r>/commits?path=<path>` for history, `gh pr view`,
  `gh run list --branch main` for real CI status.
- Linear MCP `get_issue` for attachments and state history; a ticket that
  cycled Pull Request ↔ In Progress five times is a signal on its own.
- No repo named? grep local checkouts under `~/Developer` and `gh search
code`. If it cannot be found, say so; never fabricate a root cause.
- "Related issue" across different repos is not a duplicate; verify each
  repo independently.

## Reporting

Report before/after counts by state from `linear-triage diff`, then what
the escalations found, then the raw close numbers. Never report forty
closes when thirty-five of them are one alarm family that needs one fix.
