---
name: deploy
description: Use to ship a service — build → smoke test → canary with error-rate comparison → auto-rollback on regression → post-deploy validation (tail logs 2-3 min, hit /health, check Sentry). Load before touching any deployment pipeline or writing post-deploy steps.
---

# Deploy

A deploy that succeeds without post-deploy validation is not done. Production confidence
comes from observing real behavior, not green CI.

## Gotchas (the defaults you break)

- **`mise run ci` green ≠ production healthy.** CI proves the artifact; post-deploy proves
  the running service. Both are required — one does not substitute for the other.
- **Do not tail logs for less than 2 minutes.** Error rates can be bursty. A single clean
  minute is noise. Watch the full window before declaring clean.
- **Rollback before root-cause analysis.** Mitigation takes priority. Diagnose after users
  are unblocked — not while they are blocked.
- **A 503 from `/health` is not always a crash.** Dependency unavailability (DB, cache)
  triggers 503. Check the dependency chain before escalating to "service is down."
- **Never deploy an artifact built outside the standard pipeline.** If the CI artifact is
  not the one being deployed, you have no provenance. Treat as a blocker. **Exception:**
  when Actions cannot start (`startup_failure`, spending limit), load `local-prod-deploy`
  and replay the repo's Deploy workflow from the laptop — do not invent a rolling update.

## The pipeline

**1. Pre-deploy gate**

```bash
mise run ci   # must be green locally before any deploy command runs
```

No exceptions. A red local gate means the artifact is not ready.

**2. Smoke test (pre-deploy, staging/preview)**
Exercise the changed endpoints with real-looking inputs. Assert status codes and response
shapes — not just "it didn't 500." If the service exposes `/health` and `/ready`, both
must return 200 before proceeding.

**3. Canary deploy**
Route 5–10% of traffic to the new version. Watch error rate on old _and_ new for at least
5 minutes:

```bash
# SAH — ZyINS production (profile: sah-readonly, region: us-east-1)
aws logs tail /ecs/zyins-production --since 5m \
  --filter-pattern "?ERROR ?FATAL" --profile sah-readonly --follow

# NQ — app (profile: nq-readonly, region: us-west-2)
aws logs tail /ecs/nq-app --since 5m \
  --filter-pattern "?ERROR ?FATAL" --profile nq-readonly --follow
```

**Auto-rollback gate (non-negotiable):** if the new version's error rate exceeds the old
version's by more than 2×, or `/health` returns 503 for more than 60 consecutive seconds,
trigger rollback immediately. This is a hard gate, not a judgment call.

**4. Full rollout**
Promote to 100% only after a clean canary window with no regression.

## Post-deploy validation (mandatory — run in order)

1. **Tail logs 2–3 minutes** (commands above). Zero new ERROR/FATAL lines for the changed
   code path.
2. **Hit the health endpoint**

   ```bash
   curl -sf https://<service-host>/health   # expect 200
   ```

   ZyINS: 200 = healthy, 503 = degraded.
   NQ: use `aws ecs describe-services` to read task health.
3. **Spot-check the changed functionality.** Exercise the exact user action the PR
   changed. Read the response — not just the status code.
4. **Check Sentry.** Open the project; confirm no new issues or error-rate spikes appeared
   in the deploy window.

If any step fails: **rollback first**, then diagnose. Do not debug a broken production
service in place.

## Logging standard (for code you write in this service)

Structured key=value or JSON. Include `trace_id` on every line in request context. Level
discipline: ERROR for things that need attention, WARN for recoverable issues, INFO for
normal operations worth recording. Never log secrets, PII, or full request/response bodies.
Log the _why_, not the what — the code already says what happened.
