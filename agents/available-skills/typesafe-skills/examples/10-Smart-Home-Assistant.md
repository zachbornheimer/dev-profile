---
name: 10 Smart Home Assistant
description: A speculative fan-out of TypeSafe questions handles known smart-home commands, with an LLM used only to split compound requests and to answer genuinely conversational ones.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/demos/smart-home
VIDEO: https://www.loom.com/share/18c4dbcf8db546dfb2d7f2ef018e78e4?source=embed_watch_on_loom_cta
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Building an interactive application where most requests are structured commands but some are compound or conversational, and TypeSafe should sit inside the app rather than replace its generative model outright.

## What it demonstrates

For a request like "turn off all of the lights in the house," the demo does not classify, wait, then ask what device, wait, then ask what action — it evaluates device type, domain scope, and desired action together in one speculative fan-out (see `06-Speculative-Fan-Out.md`), because "waiting to ask questions only once you are certain you need the answer" is slower and costlier than batching. TypeSafe is paired with a generative LLM for exactly two jobs it isn't designed to do itself: (1) a Noul first detects whether a request contains multiple distinct actions; if so, an LLM splits it into atomic commands and each one goes back through TypeSafe, and (2) if TypeSafe identifies a general conversational or informational request, a generative LLM writes the reply. TypeSafe decides and routes; the generative model writes only when writing is actually required. The demo app is a Vite/React single-page application, with source code promised on GitHub at release.

## Steps / call shape

```text
"turn off all of the lights in the house"
  -> TypeSafe (single call): category, domain, device_type, action, ...
  -> code reads only the fields relevant to the resolved branch
  -> executes the device action directly

"turn off the lights and lock the door"
  -> Noul: is this a compound request?
  -> yes -> LLM splits into ["turn off the lights", "lock the door"]
  -> each atomic command re-enters the TypeSafe flow above

"what's the weather like today"
  -> TypeSafe: conversational/informational request
  -> generative LLM writes the reply
```

## Results / numbers

The demo page does not publish its own cost or latency table; it demonstrates the architecture pattern from `06-Speculative-Fan-Out.md` live in an app rather than measuring it. The Loom video (linked above) is a screen-recorded walkthrough of the assistant; its content was not transcribed here — watch it directly for the live demo.

## Pitfalls

- Don't route every request through the generative LLM "just in case" — TypeSafe should own everything that fits a bounded question, and the LLM should only be reached for compound-splitting and true conversation.
- Compound-request detection is itself a bounded Noul question, not a job for the same LLM call that will do the splitting — keep the detection and the splitting as separate steps.
- This is a UI/interactive-latency use case (see `05-Confidence-and-Probabilities.md` and `06-Speculative-Fan-Out.md`) — batching the branch-specific questions up front is what keeps the perceived response fast.

## Related cookbooks

- `06-Speculative-Fan-Out.md` — the exact batching pattern this demo runs live.
- `09-Intent-Routing.md` — the routing-by-classification pattern underlying "TypeSafe decides and routes."
- `01-When-to-Use-TypeSafe.md` — the code/TypeSafe/generative-LLM boundary this demo draws in practice.
