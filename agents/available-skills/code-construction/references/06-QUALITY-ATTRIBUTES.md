# Security and enterprise reliability

Apply this file to the quality attributes the work actually affects. State a
quality claim only with a workload, boundary, metric, threshold, and executable
evidence. Otherwise mark it `NOT PROVEN`.

## Security

Identify assets, trust boundaries, actors, abuse cases, and failure impact before
choosing controls. Validate at every external boundary. Authorize at the
mutation, not only at an outer handler. Use least privilege, safe path handling,
bounded input, explicit resource limits, and fail-closed defaults.

Validate security-relevant identity before normalization can erase evidence.
For example, resolving a path must not make a symbolic link look like an
ordinary trusted path. Keep the original input and canonical form when both are
needed, and define which checks apply to each.

Keep secrets out of source, logs, fixtures, command arguments, reports, and
generated artifacts. Scan dependencies, source, configuration, infrastructure,
containers, and secrets as applicable. A static-analysis or lint task is not a
secret scanner. The public scan task must include a scanner that fails when a
safe synthetic secret is present in a file the scan is required to inspect.
Prove each scanner with that finding; a green scanner that did not inspect the
file is a failure.

Add adversarial tests for the actual boundary: traversal and links for files,
injection and authorization for APIs, replay and duplication for events, and
resource exhaustion for public inputs.

## Concurrency and mutable state

Name the consistency model and identity token. Bind a decision to the exact
observed version and validate it immediately before its consequential effect.
Test the unsafe interleaving deterministically at that seam. Time, size, names,
and retry counts are not authoritative identity unless the domain proves they
are. Same-size content with a restored modification time is still a different
version. Reject and restore that change instead of treating the file as
unchanged.

Validation followed by mutation is still a race when another actor can change
state between those operations. Prefer an atomic conditional mutation. If the
platform cannot provide one, make that limitation explicit and use a design that
detects the resulting identity, preserves recoverability, and safely rejects or
compensates for a stale effect. A last-moment test hook must be able to prove the
unsafe interleaving; a check slightly earlier in the call stack is not proof.

Do not describe a check as atomic merely because it is adjacent to the effect.
Test at the actual primitive that commits the effect. When a mutation primitive
cannot compare the expected version atomically, verify the resulting object or
state after that primitive and restore or compensate before reporting success.
The outcome remains changed, conflicted, or unknown unless that verification
proves the planned version was the one affected.

Make idempotency keys, lock ownership, retry ownership, and conflict behavior
explicit. Mechanical transport retries do not own product retry policy.

## Resilience and recovery

Define behavior for timeout, partial failure, duplicate delivery, restart,
dependency outage, corrupt state, and exhausted retry budget. Bound every wait,
retry, queue, batch, and external call. Use backoff and jitter where retries are
safe. Preserve enough durable state to resume or compensate without duplicating
effects.

Test failure injection through owned ports. Prove restart recovery and partial
result reporting through the public path. Never convert an unknown or incomplete
result into success.

## Observability

Pure policy returns structured reasons and evidence; the shell emits logs,
metrics, traces, and audit records. Include operation identity, version basis,
outcome, duration, retry or conflict state, and safe correlation fields. Exclude
secrets and unnecessary personal data.

Alerts correspond to user or operator action. Health checks distinguish process
life from dependency readiness. Verify telemetry during real success and failure
paths, not only by checking that logging calls exist.

## Scale and performance

Translate “enterprise scale” into a workload: item count, request rate, data
distribution, concurrency, latency target, throughput target, memory and storage
limits, and cost ceiling. Document complexity and the first expected bottleneck.

At billion-item scale, require bounded memory, streaming or partitioned work,
stable pagination or checkpoints, backpressure, resumability, skew handling, and
an explicit capacity model. Benchmark representative distributions and failure
modes. Extrapolation is a hypothesis until a measured curve supports it.

## Reproducible proof

Evidence records include exact input and treatment hashes, tool and runtime
versions, commands, exit status, duration, stdout and stderr, environment key
names without secret values, produced artifact hashes, and known limitations.
Keep generation separate from evaluation so a model cannot award itself a pass.
