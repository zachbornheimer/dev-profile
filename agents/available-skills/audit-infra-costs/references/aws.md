# AWS reference — commands, unit prices, account facts

The read-only cheat sheet for auditing AWS accounts. Every verb here is
`get-*`, `describe-*`, `list-*`, or read-only `pi`/`logs` queries — that is the
audit discipline, and because these profiles hold root credentials it is also
the safety rule.

## Known profiles and accounts

| Profile     | Account                 | Notes                                    |
| ----------- | ----------------------- | ---------------------------------------- |
| `sah`       | 514598028285            | work account, primary region `us-west-2` |
| `nq`, `zab` | other personal accounts | audit only if asked                      |

Root credentials are in use on these profiles — read-only verbs are mandatory,
not a preference.

## Cost Explorer — the cost pivot

Six months, unblended, pivoted by service:

```bash
aws ce get-cost-and-usage \
  --profile sah --region us-west-2 \
  --time-period Start=$(date -u -v-6m +%Y-%m-%d),End=$(date -u +%Y-%m-01) \
  --granularity MONTHLY --metrics "UnblendedCost" \
  --group-by Type=DIMENSION,Key=SERVICE \
  --output table
```

Same call with `Key=USAGE_TYPE` decomposes a service line into its unit
components (ACU-hours vs storage vs I/O, vCPU-hours vs GB-hours) — that is how
you attribute dollars to units instead of to a brand.

## Utilization — measure, don't assume

RDS/Aurora top SQL via Performance Insights:

```bash
aws pi get-resource-metrics --profile sah --region us-west-2 \
  --service-type RDS --identifier <db-resource-id> \
  --start-time $(date -u -v-7d +%FT%TZ) --end-time $(date -u +%FT%TZ) \
  --metric-queries "Metric=DataLoad,GroupBy=db.load.avg,db.sql_tokenized" \
  --period 604800 --output table
```

CloudWatch metric names worth pulling:

- **RDS/Aurora**: `CPUUtilization`, `DatabaseConnections`,
  `VolumeReadIOPs`/`VolumeWriteIOPs`, `FreeableMemory`, ACU variance over time
  for Serverless v2 (`ACUUtilization` — a flat line at min ACU means the
  autoscaling range is set wrong or the DB is idle).
- **ECS/Fargate**: service-level `CPUUtilization` and `MemoryUtilization`
  (`ECS/ContainerInsights` or `AWS/ECS` namespace). Judge services by _average_
  CPU: 0.0–4.7% avg means the allocation, not the traffic, is the problem.

## Unit prices observed (us-west-2, 2026 audit)

- Aurora Serverless v2: **$0.12/ACU-hour**, **$0.10/GB-month storage**,
  **$0.20 per million I/O requests**. (Oct sample: 27,960 ACU-hrs ≈ $3.4k,
  3,619 GB ≈ $362, 2.4B I/O units.)
- Fargate: **$0.04048/vCPU-hr** and **$0.004445/GB-hr** (x86);
  **$0.03238/vCPU-hr** and **$0.00356/GB-hr** (ARM). A 2×8-vCPU x86 service
  idling is ~$58/mo per replica in compute alone.
- ALB: **$0.0225/hr** + **$0.008/LCU-hr** — 13 ALBs ≈ $213/mo before traffic.
- Public IPv4: **$0.005/hr** per address (~$3.65/mo each).
- KMS customer-managed key: **$1/mo each** — 693 keys ≈ $699/mo, most guarding
  resources where the AWS-managed key was fine.
- CloudWatch custom metrics: **$0.30/1,000 metrics** past the free tier;
  1,240 custom metrics ≈ $598/mo with alerting.
- Business Support: starts at **$100/mo** + 10% of the first $10k, 7%… down a
  tiered scale — for a 1-person shop, check what of it is ever used.
- Savings Plans / RIs: typically 25–60% off equivalent on-demand for committed
  spend; 0% coverage on stable load is the standing finding.

## Red-flag inventory commands

```bash
aws rds describe-db-clusters --profile sah --region us-west-2
aws rds describe-db-instances --profile sah --region us-west-2
aws ecs list-services --profile sah --region us-west-2 --cluster <c>   # then describe-services for CPU/memory
aws elbv2 describe-load-balancers --profile sah --region us-west-2
aws ec2 describe-addresses --profile sah --region us-west-2            # idle public IPv4s
aws kms list-keys --profile sah --region us-west-2                     # then list-aliases to count real CMKs
aws ce get-cost-and-usage ... --group-by Type=DIMENSION,Key=USAGE_TYPE
```

Look for: ECS services whose names mention `preview`, `pr-`, `demo`, `test`;
ALBs with no healthy targets; replicas whose `DatabaseConnections` has been ~0
for a month; KMS aliases one-per-resource.

## Savings-coverage follow-up (after "0% SP/RI coverage" is found)

```bash
# AWS's own engines price the commitment for you — never hand-compute it:
aws ce get-savings-plans-purchase-recommendation --savings-plans-type COMPUTE_SP --term LENGTH_ONE_YEAR --payment-option NO_UPFRONT ...
aws ce get-reservation-purchase-recommendation --service "Amazon Elastic Compute Cloud - Compute" ...
aws ce get-cost-and-usage --group-by Type=DIMENSION,Key=SERVICE   # Bedrock splits BY MODEL here
```

The recommendation engines return the exact $/mo saving and % — cite their
output rather than a list price. And group Bedrock by SERVICE (not USAGE_TYPE)
to attribute an AI burst by model before saying it is unattributable.
