---
name: audit-infra-costs
description: >-
  Run a read-only cloud-infrastructure cost audit: attribute every recurring dollar
  to a specific resource, measure real utilization, and produce a ranked savings
  plan with guardrail checks. Use whenever the user asks why their cloud bill is
  high, wants costs reduced/right-sized, mentions AWS/RDS/ECS/Bedrock/KMS/CloudWatch
  spend, Savings Plan or Reserved Instance coverage, idle resources, a monthly
  run-rate, or wants a cost report or infrastructure spend reviewed — also use when
  planning any change that would add a vendor, a server, or a new charge.
---

# audit-infra-costs — evidence-first cloud cost audit

Act as a **senior DevOps director and systems engineer**: you are auditing
someone's account, not selling them anything. The method is general — the
worked example below is AWS (see `references/aws.md` for commands, unit prices,
and known account facts), but the three questions transfer to any provider.

## Non-negotiables

- **Read-only discipline.** The account is audited with root credentials, so
  every command must be a `get-*`, `describe-*`, `list-*`, or Cost Explorer
  `get-*` verb. A single mutation during an audit invalidates the audit.
- **Evidence-first.** Every number in the report traces to a CLI output or
  file. If you cannot cite the command that produced a figure, the figure does
  not go in the report.

## The three questions, in order

1. **Why is it as pricey as it is?** Pivot 6 months of cost data by SERVICE,
   then by USAGE_TYPE, then cross-reference the top lines against a live
   resource inventory (`describe-*`/`list-*`). Attribute every recurring
   dollar to a _specific resource_ — "5 Aurora clusters consuming 27,960
   ACU-hours", not "RDS is expensive". A service line you cannot decompose to
   resources is itself a finding.
2. **How is it actually being used?** Measure — never assume. For each costly
   resource gather utilization vs allocation: ECS/Fargate service average CPU
   (an ECS service at 0.4% average CPU is idle, whatever its memory), RDS
   Performance Insights top SQL and connection counts, Aurora ACU variance
   over time, storage growth rate. Utilization data decides which dollars are
   waste; the cost pivot only tells you where to look.
3. **Is there a better approach?** Only after 1 and 2. Better = cheaper for
   the same reliability, or same cost for more headroom — judged against the
   doctrine below, not against a vendor's landing page.

## Root-cause recursion (the manager follow-ups)

Every measurement should trigger the follow-up a good manager would ask,
until the answer names a _table and a code path_, not a service line:

1. **"Who exactly is doing this?"** Attribute the load to a resource, then
   to a caller. Constant write IOPS? Ask which table, which job, which repo —
   a service line ("RDS is expensive") is never an answer.
2. **"Does it sleep?"** Pull an hourly timeseries for a weekday AND a
   weekend. Load that never drops at 3am on Sunday is a background writer —
   queue, analytics ingest, audit hook, chatty ORM flush — not traffic.
   Traffic has a diurnal shape; machines don't.
3. **"What kind of work is it?"** Low CPU + sustained I/O means the work is
   persistence, not computation. Hunt for append-only tables, per-row
   commits that could be batched, autovacuum churn on a bloated table.
4. **"Does anything ever delete it?"** Check for retention: TTLs, partition
   drops, archive jobs. Accelerating storage growth with no deletion path
   IS the finding — say it, then price it.
5. **"Is the vendor billing the pattern?"** Per-I/O billing punishes write
   _frequency_; per-GB billing punishes _retention_. Fix the pattern the
   bill prices — batch the writes, or move that one pattern to a cheaper
   store (S3/Kinesis for event-log-shaped writes) — before moving the
   database.

Stop when the next question is answerable only by reading app code or
querying the table. Then go read it — with the owner's authorization for any
credential or network change. Never invent the answer to a question you
cannot measure yet: name the missing measurement and what it needs.

## Doctrine: optimize in place (policy)

**Always optimize on the provider we already have.** Switching providers is a
fallback, not a lever. Any accepted optimization must pass three guardrails —
all three, or the lever is rejected:

1. **Do not remove or downgrade anything whose job is to autoscale.** Autoscale
   capacity is insurance, not waste; it only looks idle on a quiet day.
2. **Do not create more maintenance work.** Provisioning a server that needs
   patching where serverless didn't is a regression — count the ops cost in the
   savings math, especially for a 1-person team.
3. **It must be easy to do and maintain.** A clever savings trick nobody
   understands in six months is a liability.

Provider-switch analysis (Fly/Railway/Render/DigitalOcean/Neon/Supabase/…) is
only run when in-place levers are exhausted or blocked, and must be grounded in
Terraform/OpenTofu Registry facts: provider address, official vs community
tier, last release date, and hard caps (a 3.6 TB Postgres cannot move to a
platform with a 1 TB cap, and Neon/Supabase cost _more_ at that size — a
storage cap or a higher unit price kills the switch before "we like the
dashboard" can save it).

## Change workflow for an accepted lever

Zach's standard procedure — every accepted lever goes through all five steps:

1. **Codify** the change in OpenTofu first. The code is the source of truth, so
   write the change there before touching the cloud.
2. **Dry-run** with `tofu plan`. The plan shows exactly what would be created
   and destroyed. Review it line by line — a plan you didn't read is a change
   you didn't review.
3. **Apply manually over the CLI** with the provider's tools — not `tofu apply`.
   The console/CLI change is the real mutation; the plan was only the preview.
4. **Reconcile** so the OpenTofu code remains the truthful record of what
   exists.
5. **Verify compliance parity.** Compliance must stay the same or get easier.
   Each new vendor added is a new subservice in the SOC 2 trust-services
   mapping; for a 1-person company that audit cost is real money and must be
   counted against the savings.

## Report template

Structure every audit report exactly this way:

**Recurring charges** — one row per charge:

| Charge | Resource | Qty | $/month |
| ------ | -------- | --- | ------- |

**Measured use** — utilization evidence for each costly resource:

| Resource | Allocated | Measured use | Source command |
| -------- | --------- | ------------ | -------------- |

**Savings plan** — one row per lever, ranked by dollars:

| Lever | Saves $/mo | Autoscale preserved? | Maintenance unchanged? | Easy + maintainable? | Codified? | Compliance parity? |
| ----- | ---------- | -------------------- | ---------------------- | -------------------- | --------- | ------------------ |

A lever with any ✗ is explained or dropped, never quietly included.

**Provider comparison (fallback only)**: provider address, tier, last release,
storage caps, unit prices, verdict.

## Red flags checklist

Hunt for these — each was a real dollar in the audited account:

- **0% Savings Plan / Reserved Instance coverage** on stable, predictable load
  — everything on-demand is a standing discount left on the table.
- **Per-resource KMS key sprawl** — hundreds of $1/mo customer-managed keys,
  one per resource, mostly on things that don't need a CMK.
- **Idle public IPv4 addresses** at $0.005/hr each (~$3.6/mo per address;
  94 addresses ≈ $355/mo).
- **PR previews deployed as permanent services** — an ECS service that was a
  demo and never got cleaned up.
- **Massively over-provisioned compute** — e.g. 2×8-vCPU containers idling at
  0.4% CPU.
- **Unused read replicas** — billed 24/7, queried never.
- **CloudWatch custom-metric sprawl** — 1,000+ custom metrics at ~$0.30/100
  with nothing reading them.
- **Business Support tier** for a tiny team — check the tier's minimum spend
  against how much of it is ever used.
- **Unbudgeted usage-driven AI spend** — Bedrock/API bills that scale with
  usage need their own budget alarm, not a surprised line in the invoice.

## Filing findings

File every accepted finding as an **atask objective** with one obvious proof
command (see the `atask` skill). Never claim done without tool evidence — a
finding's proof command is how a later worker demonstrates the savings landed.
