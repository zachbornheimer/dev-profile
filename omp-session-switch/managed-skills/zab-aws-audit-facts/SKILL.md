---
name: zab-aws-audit-facts
description: "Use when auditing or costing the AWS zab profile (account 443021256344, us-east-1, bpp/zysys hosting), or when asked whether a tool exists for AWS cost audits; holds measured baseline, CLI gotchas, and the fact that no callable audit tool exists yet."
---

# zab AWS audit facts (measured 2026-11-09, read-only)

Procedure lives in the `audit-infra-costs` skill (user-authored; do not edit). This skill only holds account facts and gotchas it lacks.

## No audit tool exists
Searched tool catalog, `~/.omp/agent/tools`, capability-replicas/extensions/mcp.json: nothing. `/force <tool>` has nothing to force. Long-term home is a Mastra tool/workflow (`infra_cost_audit`); not yet built or filed. Do not invent a tool name.

## Account baseline (profile `zab`, us-east-1, single account, no Org split)
- ~$173/mo steady (May-Oct $168-190). Aug 2026 one-off $3,867: Bedrock Aug 10-23 (Sonnet 5 $2,567, Haiku 4.5 $1,006, Opus 4.7 $124; peak $1,018 on Aug 18). Invocation logging off. Budgets exist: `account-monthly-300`, `bedrock-monthly-100`.
- EC2: `production-web-server` m6a.large ($64/mo), `production-database-server` t4g.medium ($25/mo). 6 gp3 volumes, 500 GB. 2 EIPs. 63 snapshots (DLM policy: daily, retain 7). Only us-east-1 has instances.
- 0% Savings Plan coverage. Compute SP 1yr no-upfront rec: $0.092/h commit, saves ~$20.26/mo. EC2-instance SP rec returns None. Standard RI m6a.large alone ~$21.31/mo.
- Web server CPU 99.9% every day Oct 10-26, ~6% from Oct 27 (cause not investigated; malware cleanup was Aug 4). DB CPU <1%, credit balance at cap 576; memory unmeasured (no CWAgent).
- Provisioned gp3 throughput above 125 MB/s baseline billed $5.40/mo; 3-day peaks web 144 MB/s, DB 7.3 MB/s.
- Legacy "bpp" AMIs/snapshots 2020-2022 and a 160 GB `oct21` snapshot: 224 GB total; keep Aug-4-2026 `incident-*` and `*-pre-wordpress-remediation` AMIs.

## CLI gotchas
- Profile `zab` is root creds; `iam get-account-summary` returns InvalidClientTokenId, so root key hygiene is unverifiable.
- `cloudwatch get-metric-statistics` limit 1440 datapoints: 5-min period needs a window of 5 days or less.
- `ce get-savings-plans-purchase-recommendation` uses `--term-in-years ONE_YEAR --lookback-period-in-days SIXTY_DAYS` (not `--term`).
- `aws support` fails (no Premium Support) = no Business Support charge.
- Chaining many aws calls in one `run_command` may trip the onPreToolUse 30s extension timeout; split into smaller commands or background.
- Hetzner price page (cpx32 EUR 35.99, cpx22 EUR 19.99) read 2026-11-09 showed EU/SG only and "unavailable"; volume price and registry tier unread (UNVERIFIED). Provider switch not justified (~$40-60/mo before migration + SOC 2 subservice).
