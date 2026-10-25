---
name: oncall
description: Use when a Sentry alert or PagerDuty page arrives — enrich the alert across CloudWatch, Linear, recent deploys, and Slack, then disposition it (false-positive / real / noise) with a confidence score and evidence summary. Load before investigating any production alert.
---

# On-Call Alert Triage

Alerts arrive as isolated signals. Context turns noise into a clear disposition. Enrich
first, conclude second — never the other way. Anthropic's CLUE system dropped false-positive
rate from 33% to 7% by enriching _every_ alert with internal context before a human saw it.
That's the bar.

## Gotchas (the defaults you break)

- **A timed-out tool call is not a "no errors" signal.** A CloudWatch call that returns empty
  or errors means the _tool_ failed, not that the service is healthy. Retry with a narrower
  window; if it keeps timing out, label that "infrastructure uncertainty" — not "clean."
- **Never take a corrective or destructive action on a guessed cause.** Kill, restart,
  rollback — none of these until you have direct evidence (the actual error in the log, the
  ECS task status, the alarm datapoints). A plausible story is not a diagnosis.
- **One alert can have three different root causes.** Name the cause before you name the
  action. Distinguish: app bug / infra failure / alert misconfiguration.
- **Sentry first, CloudWatch second.** Sentry gives you the stack trace and affected-user
  count in seconds. CloudWatch gives you the volume and timing. Start with Sentry.

## Enrichment protocol

PagerDuty dispatches include `aws_account_id`, `log_group`, and `alarm_name` — use them.

**1. Pull the raw signal**

- Sentry: fingerprint, stack trace, affected users, first/last seen, environment.
- CloudWatch alarm: alarm description, triggering datapoints, comparison operator.

**2. Correlate in CloudWatch — read-only profiles only**

| Profile        | Account            | Default region |
| -------------- | ------------------ | -------------- |
| `sah-readonly` | SAH `514598028285` | `us-east-1`    |
| `nq-readonly`  | NQ `257336559192`  | `us-west-2`    |

```bash
# SAH — ZyINS production
aws logs tail /ecs/zyins-production --since 15m \
  --filter-pattern "?ERROR ?Error ?error ?FATAL ?Fatal ?fatal" \
  --profile sah-readonly --region us-east-1

# SAH — PagerDuty relay / quoter
aws logs tail /aws/lambda/sah-prod-pagerduty-relay --since 15m --profile sah-readonly --region us-east-1
aws logs tail /ecs/freefexquoter --since 15m --profile sah-readonly --region us-east-1

# NQ — app and workers
aws logs tail /ecs/nq-app        --since 15m --filter-pattern "?ERROR ?FATAL" --profile nq-readonly --region us-west-2
aws logs tail /ecs/nq-app-worker --since 15m --filter-pattern "?ERROR ?FATAL" --profile nq-readonly --region us-west-2
```

**3. Check ECS task health**

```bash
aws ecs describe-services --cluster <cluster> --services <service> \
  --profile <readonly> --region <region>
```

Look for: task cycling (rapidly starting/stopping), `OOMKilled`, a deploy in progress that
overlaps the alert window.

**4. Hit the health endpoint**

- ZyINS: `GET /health` → 200 healthy, 503 degraded
- NQ: derived from `describe-services` task health

**5. Check recent deploys**

```bash
gh deployment list --repo <org/repo> --limit 10
```

A deploy in the 30 min before the alert window is the first hypothesis to test, not the last.

**6. Internal context**
Check Slack for planned maintenance or team discussion that matches the alert window.
Check Linear for open incidents or known issues on the affected service.

## Disposition

TypeSafe gate (optional, fail-open):

1. Write `{alert, sentry, cloudwatch, ecs, health, deploys, linear, slack}` to `state.json`.
2. `python3 ~/.agents/skills/typesafe-ai/scripts/typesafe.py classify-oncall --json < state.json`
3. If `source` is `typesafe`, use `disposition`, `cause_class`, `sev`, and `confidence_band`.
4. If `source` is `fallback` or `disposition` is `unknown`, continue with the table below.

After enrichment, assign exactly one:

| Disposition        | Meaning                                                                      |
| ------------------ | ---------------------------------------------------------------------------- |
| **False positive** | Evidence shows normal behavior; the rule is wrong or the threshold is wrong. |
| **Real**           | Evidence confirms user impact or service degradation. Assign SEV-1/2/3.      |
| **Noise**          | Alert fired on a non-symptom (e.g. CPU spike with no error-rate change).     |

State: **confidence** (high / medium / low), **evidence** (what you observed, which source,
over what window), and — for real alerts — the next required human action.

Do not close a "real" alert as "investigating." State the cause, or state "cause unknown —
escalating" with everything you _do_ know attached.
