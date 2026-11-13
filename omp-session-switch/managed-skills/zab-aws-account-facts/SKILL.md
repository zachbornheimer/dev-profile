---
name: zab-aws-account-facts
description: "Facts and CLI gotchas for the zab AWS profile (account 443021256344, us-east-1) when running audit-infra-costs or any cost/infra question about ZAB AI / zysys hosting AWS spend."
---

Companion to `audit-infra-costs` (its references/aws.md only lists `zab` as "other personal account"). Baseline from the 2026-11-09 audit; re-measure before quoting.

## Account
- Profile `zab`, region us-east-1, root creds (read-only verbs only). Single account, no Organization split (LINKED_ACCOUNT shows only itself).
- Steady-state bill ~$170-190/mo. Aug 2026 one-off $3,867 = Bedrock burst Aug 10-23 (Sonnet 5 $2,567, Haiku 4.5 $1,006, Opus 4.7 $124), Bedrock invocation logging OFF, spend $0 since Aug 27. Budgets: `account-monthly-300`, `bedrock-monthly-100`.
- Resources: `production-web-server` i-06e7c0292483e95d6 (m6a.large, EIP, vols 160+40+40 GB), `production-database-server` i-073f501d9a5ed0453 (t4g.medium, EIP, vols 160+80+20 GB), all gp3 3000 IOPS; two provisioned-throughput vols (web 206 MB/s, db 179 MB/s vs 125 baseline free). DLM policy `policy-0eb93651d0e4a1aab` daily 04:00, retain 7, tags Backup=true+Environment=production. No NAT GW, no other-region instances (us-west-2/us-east-2/us-west-1 checked).
- Incident history: Aug 4 2026 malware on web server; AMIs `incident-*` / `*-pre-wordpress-remediation-20260804` are forensic - keep until owner decides retention. 8 legacy 2020-2022 "bpp" AMIs/snapshots (8 GB each) and a 160 GB `oct21` manual snapshot are cleanup candidates (billed size unverified; snapshots are incremental).
- Web server CPU was 99.9% daily Oct 10-26 then ~6% from Oct 27: investigate before any downsizing. DB is idle (0.3-0.9% CPU, credit balance pinned at cap) but memory is UNMEASURED (no CWAgent metrics) - get `free -m` / buffer-pool before proposing t4g.small.
- AWS recommendation engines (60-day lookback): Compute SP 1yr no-upfront $0.092/h -> $20.26/mo (23%); Standard RI m6a.large -> $21.31/mo (34%). EC2_INSTANCE_SP returned None. Don't stack SP and RI.

## CLI gotchas (cost auditing)
- `cloudwatch get-metric-statistics`: max 1440 datapoints per call. 14d at 300s fails; use <=3d at 300s or longer periods. A single 30d period returns bucket-split datapoints - use `--period 86400` for a daily series.
- `ce get-cost-and-usage` End date is exclusive; first-of-month ranges work. Bedrock models appear as separate SERVICE lines.
- `bedrock get-model-invocation-logging-configuration` returning empty = logging not configured. CloudTrail `lookup-events` has only management events, so Bedrock InvokeModel callers are not recoverable.
- `iam get-account-summary` returned InvalidClientTokenId on this profile; root key hygiene unchecked.
- `run_command` can hit a 30s `onPreToolUse` extension timeout when many aws calls are batched in one command; split into smaller calls.
- `support describe-severity-levels` -> SubscriptionRequiredException = no paid support plan.
