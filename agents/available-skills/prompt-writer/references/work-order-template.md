# Work-order template

Copy the fence below verbatim into the top of the Agent/Task prompt, then
replace every placeholder value. The placeholders are deliberately chosen to
pass `work-order-gate.sh` unmodified — the shape is right; only the content
is a stand-in.

```yaml
work_order:
  schema_version: 1
  intent: "<one sentence — the outcome, not the method>"
  scope:
    primary_targets:
      - "<file the order centers on>"
    allowed_writes:
      - "<glob the worker may modify — often the same as primary_targets>"
    required_inputs:
      - "<file the worker must read first — omit this key if none beyond primary_targets>"
    given:
      - "<facts/artifacts already established — the worker must not redo them>"
  acceptance:
    - id: "<short-id>"
      kind: command
      run: "<the exact command the harness runs after the worker finishes>"
      expect:
        exit_code: 0
```

**How to fill it:** replace every `<...>` placeholder with the real value;
delete `required_inputs` entirely if there's nothing to read beyond
`primary_targets`; add prose below the fence for the _why_, non-goals, and
anything `intent` is too short to say (see `work-order-example.md` for a
fully worked one, and `work-order-protocol.md` for why the fence is shaped
this way).

Run `work-order-gate.sh --check <file>` (or pipe the prompt in with `-`) on
anything non-trivial before spawning — it runs the same normalize → validate
→ policy path a real spawn hits, with no state writes, and prints either the
normalized order plus `OK` or the errors JSON.
