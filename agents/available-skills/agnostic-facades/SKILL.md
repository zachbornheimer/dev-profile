---
name: agnostic-facades
description: Use when designing, writing, or reviewing a domain workflow that talks to a vendor, provider, queue, store, harness, or other swappable backend. Use when adding a second provider, choosing a mechanism, when a workflow already names a vendor, or when the user says agnostic facade, ports and adapters, or /agnostic-facades.
---

# Agnostic facades

A workflow names domain capabilities and effects, never concrete providers or mechanisms.

The test is not “did we inject an interface?” The test is:

> Can another provider be added without changing the workflow, its tests, or the shared domain model?

If those must change, the boundary is leaking.

This is not the code-style edge rule (inject filesystem, time, HTTP, randomness so tests can fake I/O). That isolates effects. This isolates **provider choice from domain workflow**.

Production instance of the same shape: Flight `src/webhooks/receiver.ts`. Do not fork its ingress laws here.

## Four roles

| Role     | Owns                                     |
| -------- | ---------------------------------------- |
| Workflow | Domain sequence, decisions, and statuses |
| Port     | The contract the workflow needs          |
| Adapter  | One concrete provider or mechanism       |
| Host     | Construction and composition only        |

The workflow is not the facade. The vendor-free boundary around it is.

Define a port next to its consumer. Keep credentials, SDK types, vendor stores, and provider translation inside the adapter.

## Two port kinds

| Kind       | Question it answers        | Chosen                   | `matches`? |
| ---------- | -------------------------- | ------------------------ | ---------- |
| Capability | Can you handle this input? | Runtime, from candidates | Yes        |
| Mechanism  | Perform this effect.       | Host, at composition     | No         |

No provider enum or vendor switch in the workflow. No runtime rediscovery on a mechanism the host already chose.

## Capability shape

Claim, prove, and translate stay three methods. Fusing them smuggles provider control flow into the workflow. Not required on every port — only on runtime-selected capability adapters.

```text
interface Format:
    matches(blob) -> boolean     # claim: I recognize this
    validate(blob) -> void       # prove: it is valid for me
    read(blob) -> Document[]     # translate: provider → domain

interface Store:
    save(document)

class Ingest:
    constructor(formats, store)

    run(blob):
        format = first where format.matches(blob)
        if format is absent:
            return Rejected

        try:
            format.validate(blob)
            documents = format.read(blob)
        catch ExpectedRejection:
            return Rejected

        for document in documents:
            store.save(document)

        return Saved
```

Host composes `Ingest([CsvFormat(), JsonFormat()], DurableStore(config))`. A third format is a new class plus a list entry. `Ingest.run` does not change.

First match wins unless the domain names another policy. No match is an explicit domain outcome, not a default provider.

## Mechanism ports

```text
interface Store:
    save(document)
```

The host passes `DurableStore(config)`. The workflow does not ask the store whether it matches the environment.

## Domain model

Provider data may enter as opaque input. It does not grow fields on a shared record merely because the first provider exposed them.

A field belongs in the domain when the **domain** owns the concept — would it still belong if the first provider disappeared? If not, translate it inside the adapter.

`origin` is persistence metadata, not a branch key. Switching on `origin` in the workflow is the enum leak with a softer name.

## Error boundary

Expected provider rejection may collapse into a domain result (`invalid signature`, `unsupported payload` → `Rejected`).

Unexpected programming, infrastructure, or availability failures must stay distinguishable (`database down`, `broken invariant` ≠ `Rejected`).

The boundary removes vendor semantics. It does not hide operational failure.

## Laws

1. New provider = new adapter + host composition. Workflow file unchanged.
2. Capability selection is first-match-wins unless the domain specifies another policy. No match is a domain outcome, not a default provider.
3. Mechanisms are host-selected. They do not need `matches`.
4. Provider details stop at the adapter: SDK types, credentials, error text, provider-only fields.
5. Expected provider failures collapse into domain semantics. Unexpected failures do not.
6. Workflow tests use port fakes. Constructing a vendor request, SDK type, or concrete adapter in a workflow test means the boundary leaked.
7. Adapter tests live with the adapter.
8. Grep the workflow for provider names: zero hits.
9. Domain fields are not provider-shaped by default.

When reviewing, walk 1–9. The replacement test is law 1 asked of the diff: if a second provider lands tomorrow, only the new adapter, host composition, and adapter tests change.

## Default misses

| Miss                                          | Instead                                     |
| --------------------------------------------- | ------------------------------------------- |
| `if provider == "…"` in the workflow          | Adapter `matches`                           |
| `new ConcreteAdapter()` inside the workflow   | Host composition                            |
| A service/manager that holds every branch     | Workflow + port + adapters                  |
| Vendor types in workflow signatures           | Domain input and output                     |
| Provider-only fields on shared records        | Opaque payload, or translate at the adapter |
| Workflow tests importing a concrete adapter   | Port fakes                                  |
| `matches` on a mechanism port                 | Host already chose                          |
| `catch` everything as rejected                | Collapse only `ExpectedRejection`           |
| “We injected an interface, so it is agnostic” | Run the replacement test                    |

## When not to load

One intentionally hardcoded backend, no credible second provider, and provider selection is not a domain problem — the edge facade is enough. Do not add runtime selection for symmetry.

Framework types may stay at the framework edge. Wrap them only when the wrap earns a domain job (for example, a one-shot body that both prove and translate must read).
