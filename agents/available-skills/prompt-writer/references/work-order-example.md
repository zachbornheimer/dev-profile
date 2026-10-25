# Work-order example

One complete, ready-to-copy Agent/Task prompt in the structured format
`work-order-gate.sh` requires. Adapted from the clarify-hook example in
`work-order-protocol.md`. Copy the fence verbatim; only the field values change.

```yaml
work_order:
  schema_version: 1
  intent: "Preserve the runner's scoped CLI arguments through a decision so the clarify hook's suppression logic stops dropping them."
  scope:
    primary_targets:
      - internal/clarify/feedback/feedback.go
      - internal/app/clarify_hook.go
    allowed_writes:
      - internal/clarify/rules/**
      - internal/clarify/feedback/feedback.go
      - internal/app/clarify_hook.go
    required_inputs:
      - internal/clarify/violation.go
    given:
      - "Root cause already found: feedback.go rebuilds argv from violation.Command instead of the original invocation."
  acceptance:
    - id: clarify-tests
      kind: command
      run: go test ./internal/clarify/... ./internal/app/...
      expect:
        exit_code: 0
    - id: ci
      kind: command
      run: mise run ci
      expect:
        exit_code: 0
    - id: stop-payload
      kind: command
      run: go run ./cmd/zq clarify --claude-hook < testdata/stop-payload-scoped-runner.json
      expect:
        stdout_contains:
          - "[voice] 2×"
        json_keys_absent:
          - decision
```

A test fixture proved feedback.go drops the runner's `-run` / `-short` flags
once a suppression decision fires, because the decision path rebuilds the
command from `violation.Command` instead of the original argv. Fix that path
so a scoped runner invocation survives a decision unchanged.

Non-goals: do not touch the suppression heuristic itself, only argument
preservation. Do not add a new config flag for this — the fix is structural.

---

Every field above is required except `scope.required_inputs` (omit when there's
no reading beyond the primary targets). No `execution` block — set `model`,
`effort`, `isolation`, `turn_cap`, `token_budget` as spawn parameters; the gate
compiles them in with defaults from `schemas/work-order-defaults.json`.

The prose block below the fence is unstructured but not optional: it carries
the _why_ (what a reader can't get from `intent` alone) and any non-goals. Keep
it short — the fence already did the structural work.

**Repair by reference, don't regenerate.** If `work-order-gate.py` denies the
order, it has already stored the full prompt. The reason stays small enough
that a 1KB truncation still shows every field:

```json
{
  "order_ref": "3f9a...",
  "missing": ["acceptance"],
  "example_path": "/abs/path/3f9a....txt"
}
```

`missing` is key names only. `example_path` is the fence to paste: a
`work_order_patch` for that field, not a full work_order scaffold. Read the
file and resend nothing but the `order_ref` line plus its contents. The gate
restores the stored prompt and merges the fragment in, so the original prose
never gets retyped:

````text
order_ref: 3f9a...

```work_order_patch
[{"op": "add", "path": "/work_order/acceptance", "value": [{"id": "clarify-tests", "kind": "command", "run": "go test ./internal/clarify/...", "expect": {"exit_code": 0}}]}]
```
````

A second failed repair denies again under the same `order_ref`; one left
unrepaired for 24h expires and needs a fresh full order.
