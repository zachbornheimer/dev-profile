# Work-order protocol (owner design, 2026-09-16)

Status: design. First build is the validation-error and field-patch protocol; schema sophistication comes after.

## Owner's design

I like the direction. The schema solves **shape consistency**, but the larger win comes from making validation and repair incremental rather than forcing regeneration.

The strongest design would be:

```text
prompt writer
    ↓
structured work order
    ↓
normalize → validate → policy-check
    ↓               ↓
 valid          field-level patch
    ↓               ↓
immutable compiled spawn request
    ↓
subagent
    ↓
diff enforcement + independent verification
```

My main adversarial concerns:

- **Two sources of truth.** `model`, `effort`, `isolation`, budgets, etc. exist both in the work order and Agent invocation. Cross-checking catches disagreement, but creating disagreement is avoidable. I would make the harness authoritative for execution parameters and keep the work order focused on the task. If you want them visible, have the harness inject them into the compiled header.
- **Schema failure still causes wasted tokens unless repair is designed explicitly.** On validation failure, don't ask for another work order. Return something like:

  ```json
  {
    "errors": [
      {
        "path": "/work-order/done_when",
        "code": "minItems",
        "message": "must contain at least 1 item"
      }
    ]
  }
  ```

  Then accept only a JSON Patch / field patch. The original prose never gets regenerated.

- **`blast_radius` isn't actually enforcement.** A model can declare two files and edit twelve. Treat this as `allowed_writes` and check the resulting filesystem/git diff. Undeclared writes should fail or trigger an explicit scope amendment.
- **Path safety should not live in JSON Schema.** The `isolation:none` regex is brittle. `~`, `..`, symlinks, alternate repo paths, case sensitivity, and `scratchpad_evil` create edge cases. Normalize paths in code and ask a policy function: `is_repo_path(resolvedPath)`.
- **`done_when` remains largely unstructured.** `minLength: 10` prevents empty garbage but not `"everything should work properly"`. The most valuable part to structure is verification.

I would change that portion to something closer to:

```yaml
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
    run: <fixture command>
    expect:
      stdout_contains:
        - "[voice] 2×"
      json_keys_absent:
        - decision
```

Now the harness can execute verification instead of trusting a subagent's prose claim.

I would also rename the scope concepts:

```yaml
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
```

`blast_radius` is ambiguous: does it describe expected impact, possible impact, or permission to modify? `allowed_writes` makes the security property explicit.

A few more attacks I'd design for:

1. **Scope discovery.** The agent discovers that an additional file must change. Don't make it either violate scope or restart. Give it an `amend-order` operation:

   ```yaml
   add_allowed_write:
     - internal/clarify/foo.go
   reason: interface definition must change
   ```

   Validate the amendment independently and continue the same task.

2. **TOCTOU.** Don't validate YAML and later independently construct the Agent call. Compile both from the same immutable object. Ideally record an `order_id` or hash with execution and verification output.

3. **Fake verification.** `"mise run ci exits 0"` in the order isn't evidence. The harness should run it after the worker completes and attach actual exit status/output.

4. **Worktree overconfidence.** A worktree isolates repository files, not `~/.config`, caches, network services, databases, processes, credentials, etc. Treat `worktree` as Git-write isolation, not general sandboxing.

   **Never write back to the main checkout.** A target that is untracked in git
   does not exist in a worktree branched from HEAD — the order must name it as a
   required commit (commit it before the spawn), never as a "copy it from the
   main checkout and write the result back there" instruction. Such a clause
   makes the shared checkout the write target by design, and the guards now
   refuse the write anyway.

5. **Schema evolution.** Add `schema_version: 1` immediately. Otherwise changing semantics six months from now becomes painful.

6. **Duplicate keys.** The example schema contains `"model"` twice. Many JSON parsers silently keep the latter. Make schema files themselves go through duplicate-key-aware linting.

7. **Defaults.** JSON Schema's `default` does not normally populate values. If optional fields have defaults, make the compiler inject them deterministically.

The version I'd aim for conceptually is:

```yaml
work_order:
  schema_version: 1
  intent: ...

  scope:
    primary_targets: [...]
    allowed_writes: [...]
    required_inputs: [...]

  acceptance: [...]

execution:
  model: sonnet
  effort: high
  isolation: worktree
  turn_cap: 30
  token_budget: 150000
```

But importantly, **`execution` should be emitted by the harness, not the prompt-writer**, whenever the harness already knows those values.

The key architectural principle is: **models propose semantic intent; deterministic code supplies syntax, defaults, execution policy, validation, and verification.**

That gets you much closer to your actual goal than JSON Schema alone. Instead of:

> invalid order → regenerate 600-token order + prose

you get:

> invalid `/acceptance/2/expect` → repair one field

and instead of:

> agent says it stayed within scope

you get:

> harness proves its diff stayed within scope.

I would build the patch/amendment protocol before adding much more sophistication to the schema. That's the part most directly responsible for eliminating the token waste you're targeting.

## Build order

- **(a) Structured header block:** Introduce `schema_version: 1` to support future evolution. Structure the scope with three distinct concepts — `primary_targets` (files the work order centers on), `allowed_writes` (paths the agent may modify), and `required_inputs` (files the agent must read to understand the task). Separate `acceptance` items as verifiable commands with exit codes and output patterns, replacing unstructured prose.

- **(b) Validation returns errors with field paths, never regeneration:** On schema or policy violation, return a JSON object with an `errors` array containing `{path, code, message}` for each failure. Accept a JSON Patch to repair individual fields. The original work order prose is never regenerated; validation and repair are incremental operations.

- **(c) Harness-run verification and scope enforcement:** After the worker completes, the harness executes every `acceptance` command and records actual exit codes and output. The harness diffs the filesystem/git against `allowed_writes` and fails if undeclared writes occur. Support an `amend-order` operation for scope discovery (new files the agent must change) that validates the amendment and continues without worker restart. The harness emits an `execution` block with actual model, isolation, timing, and token usage — this is evidence, not declaration.
