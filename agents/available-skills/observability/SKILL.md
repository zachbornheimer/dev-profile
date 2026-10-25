---
name: observability
description: Use when creating a new service, adding telemetry, or modifying logging/metrics/tracing. The four gotchas that make observability useless in production — and the checklist that makes it useful.
---

# Observability

In production you cannot attach a debugger. Your telemetry IS your debugger.
Design it with the same care as an API.

**Core principle:** every meaningful state change produces a structured event.
Instrument the happy path too — you need normal behavior as a baseline before
you can identify abnormal behavior.

## Gotchas — where Claude defaults break

**Vendor SDK in application code.**
No AWS X-Ray SDK, no Datadog SDK, no Honeycomb beelines in app code. Use the
OpenTelemetry SDK for your language — instrument once, export anywhere. Vendor
lock-in belongs at the collector/exporter level, not in the application. Changing
backends means reconfiguring the collector, not touching app code.

**Free-form log strings.**
`INFO: Generated quote for TX with 12 plans in 340ms` — can only be grep'd.

```json
{
  "level": "info",
  "msg": "quote generated",
  "trace_id": "abc",
  "plan_count": 12,
  "duration_ms": 340,
  "state": "TX"
}
```

This can be queried, aggregated, and correlated. Every log line in request context
must include the trace ID. That's how you go from a span to the log that explains
it.

**Alerting on causes, not symptoms.**
CPU > 80%, disk > 70%, memory > 90% → bad alerts. These are causes. High CPU that
doesn't affect users is not an incident.
Error rate > 1% for 5 min, P99 latency > 2s for 10 min, zero successful quotes in
15 min → good alerts. These are symptoms the user experiences.
Every alert links to a runbook: what does this mean, what to check first, how to
mitigate, who to escalate to.

**`/health` is NOT `/ready`.**

- `/health` (liveness): is the process running? Returns 200. No dependency checks.
  Used by load balancers. Never authenticated.
- `/ready` (readiness): can the service handle traffic? Checks database, cache, etc.
  Used by orchestrators. Returns 200 when ready, 5xx when not.
  Both are required. They are not the same.

## The three pillars (OTel)

| Pillar  | What it answers                                                     | Connect via            |
| ------- | ------------------------------------------------------------------- | ---------------------- |
| Traces  | What happened during this request, across which services, how long? | trace ID               |
| Metrics | How is the system behaving over time? Rates, durations, counts.     | exemplars              |
| Logs    | What specific event happened at this moment?                        | trace ID in every line |

All three are connected by trace context. Spike in dashboard → trace → log line.
Propagate trace context across service boundaries using W3C Trace Context headers.

## What to trace

- Every inbound request (HTTP, gRPC, message consumer)
- Every outbound call (database, API, queue, cache)
- Every significant business decision (underwriting, pricing, eligibility)

Span naming: what it does, not how. `underwriting.evaluatePlan` not `handleRequest`.
Span attributes: structured inputs relevant to debugging. Never PII, secrets, or
raw credentials.

## RED metrics (minimum for every service)

- **R**ate — requests per second (counter by route/method/status)
- **E**rrors — errors per second (counter by type/route)
- **D**uration — distribution of latency (histogram by route/method/status)
  Also: `inflight.requests` gauge. Business-specific metrics added per service.

## Auto-instrumentation first

Use OTel auto-instrumentation for your framework before writing manual spans.
Manual instrumentation is for business-specific spans — the things the framework
doesn't know about.

The OTel Collector is infrastructure, not application code. Apps send OTLP to the
collector; the collector exports to the backend(s).

## New service checklist

- [ ] OTel SDK added as a dependency
- [ ] Auto-instrumentation enabled for the framework
- [ ] Trace context propagation configured for HTTP clients
- [ ] Custom spans on significant business operations
- [ ] RED metrics exposed
- [ ] Structured logging with trace ID correlation
- [ ] `/health` and `/ready` endpoints implemented
- [ ] Alerts defined with linked runbooks
- [ ] Dashboard showing RED metrics + key business metrics

---

Full source: `~/.claude/rules/observability-standards.md`
