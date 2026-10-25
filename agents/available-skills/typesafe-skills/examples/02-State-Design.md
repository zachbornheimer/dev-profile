---
name: 02 State Design
description: Build the `state` object passed to System One as the focused evidence packet a knowledgeable reviewer would need, not a context dump.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/concepts/state
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Whenever constructing the `state` argument for a `system_one` call, especially before adding more fields "just in case" or flattening structured data into one long string.

## What it demonstrates

"State is the content you ask a System One model to evaluate. It could be a support message, a passage of text, or the current state of your application." State accepts three formats — a plain string (`"My card was charged twice."`), a structured object with named fields, or an array such as a sequence of conversation messages — and the docs recommend objects for most cases so relationships between pieces of information stay explicit. The model evaluates text-only content today; images, audio, and video are not supported.

## Steps / call shape

```python
state = {
    "ticket": {
        "message": ticket.message,
        "sender": ticket.sender,
    },
    "account": {
        "plan": account.plan,
        "open_orders": open_orders,
    },
    "policy": refund_policy,
}
```

Write questions that reference state fields explicitly by path:

```python
Noul(instructions="Does `ticket.message` request a refund?")
```

## Results / numbers

This page documents a data-format contract, not a benchmark — no cost or latency numbers are published here.

## Pitfalls

- Keep content in `state` and judgments in questions; don't fold instructions into the state object.
- Exclude unrelated history and giant context dumps — only include what a reviewer would need for the current questions.
- Name fields by the role they play (`ticket.message`), not by their storage source, so question instructions read naturally.
- If several questions need the same evidence, put that evidence in one `state` and batch the questions rather than resending it per call.
- Media (images, audio, video) is unsupported — extract textual evidence upstream and pass that in.

## Related cookbooks

- `03-Atomic-Questions.md` — the questions that read from this state.
- `13-Question-Parallel-Set.md` — measured proof that reusing one state across many questions is the cheaper architecture.
