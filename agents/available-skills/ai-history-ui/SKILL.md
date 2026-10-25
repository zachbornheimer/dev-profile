---
name: ai-history-ui
description: >
  Use when building, reviewing, or restyling an AI chat history or transcript UI —
  thinking indicators, "Thinking…" labels, tool-call / action rows, agent step
  stacks, skeleton shimmers on model work, or collapsing completed tool dumps.
  Also when the user mentions Bevel-style thinking glow or runs /ai-history-ui.
user-invokable: true
argument-hint: "[renderer | producer | inspector | review]"
metadata:
  short-description: "Thinking glow + action stack for AI turns"
  origin: "Bevel recording 2026-08-15, 38s; spec v0.1.0"
---

# AI history UI

Working work shimmers through its words. Finished work stacks underneath.
Completed history collapses so the answer is what you read.

**DELTA vs the Bevel recording:** the video leaves the tree expanded after
`done`. That is wrong for history. Collapse on terminal unless the user had
the tree open. Historical reopens are always collapsed and never shimmer.

## Load before writing code

| File                                                         | Why                                                                       |
| ------------------------------------------------------------ | ------------------------------------------------------------------------- |
| [SPEC.md](SPEC.md)                                           | Normative contract (RFC 2119). Read this.                                 |
| [spec.html](spec.html)                                       | Annotated frames, live mock, motion tokens, event log. Open in a browser. |
| [screenshots/](screenshots/)                                 | Visual ground truth. Look at the crops before painting.                   |
| [tests/spec/traceability.yaml](tests/spec/traceability.yaml) | Done-gate. Every row must become `passing`.                               |

Do not implement from a verbal memory of this skill. The screenshots are the
design. The spec is the test.

## What the output is

One transcript component that paints live and history from the same producer
event log.

```text
waiting  --send-->  working  --turn.done-->     done     --reopen-->  collapsed, no glow
                    |        --stop-->          stopped
                    |        --turn.failed-->   failed
```

A turn is exactly one of those five. "I don't know" is an invariant violation.

On screen, in order:

1. User bubble
2. Status label — `"Thinking…"` (shimmering) or `"Thought for N seconds."` (static)
3. Action tree (under the label; newest last; one live row)
4. Assistant answer — sibling below the thinking block, never inside it

## Shimmer (the thing agents get wrong)

A luminance sweep **through the glyphs**, same family as a skeleton loader.
Not a spinner. Not a percent. Not a bar. Not whole-node opacity.

```css
.shimmer {
  background: linear-gradient(
    100deg,
    color-mix(in oklch, currentColor 40%, canvas) 35%,
    currentColor 50%,
    color-mix(in oklch, currentColor 40%, canvas) 65%
  );
  background-size: 220% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: sweep 1.4s linear infinite;
}
@keyframes sweep {
  from {
    background-position: 100% 0;
  }
  to {
    background-position: -100% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .shimmer {
    animation: none;
    color: inherit;
    background: none;
  }
}
```

One clock for the status label and the single `in_progress` title. Completed
text is static. Reduced motion: static live color plus an `"In progress"`
accessibility cue. Color is never the only signal.

## Recipe

1. Paint `"Thinking…"` + Stop within 100 ms of send, before any action event.
2. Append named action rows under the status in emit order. Parent/child rails
   follow `parent_id`. Kinds in the reference: `reason` (brain), `plan`
   (sparkle), `tool` (terminal), `doc` (page).
3. Only the live row shimmers. It has no chevron and is not a hit target.
4. On `action.completed`: snap that row solid in one frame. Chevron iff
   `inspectable`. Activate opens a dismissible inspector (title = action
   title, body = payload). Missing payload → `"No details for this step."`
5. Header collapse exists only once `actions.length >= 1`. Collapse hides
   rows; identities, order, and payloads survive.
6. On `done` / `stopped` / `failed`: stop every animation, rewrite the label
   (`Thought for N seconds.` / `Stopped after N seconds.` / `Failed after N
   seconds.`), restore Send. Collapse the tree unless the user expanded it
   this turn. Never show `"Thought for 0 seconds."` — compute elapsed locally
   if `duration_ms` is missing.
7. Historical open of a terminal turn: collapsed, no shimmer, ever.
8. Answer streams below the thinking block. Unpinned overflow → jump-to-end
   chip. Pinned → follow new tokens.
9. Stop cancels in-flight work. Late events after cancel are ignored.
10. Status is a polite live region. Action start is announced. Inspectable
    rows are keyboard-activatable. Touch targets ≥ 44×44 pt. At 50+ actions,
    virtualize the expanded tree.

Producer: emit `turn.accepted`, `action.started`, `action.completed` /
`action.failed`, then `turn.done` / `turn.stopped` / `turn.failed`. One
`in_progress` peer at a time — complete or fail the live row before starting
the next sibling. The renderer self-heals a second live peer by completing
the older one and treats that as a producer bug.

Event log shape and the Bevel replay are in `spec.html` § Events.

## Default failures

| Default                                             | Contract                                                |
| --------------------------------------------------- | ------------------------------------------------------- |
| Spinner / bar / `%` / pulsing bubble                | Glyph sweep only (REQ-002)                              |
| Wait for first tool event to show chrome            | 100 ms after send (REQ-001)                             |
| Replay shimmer on a scrolled-back turn              | Historical = collapsed + static (INV-005, REQ-009)      |
| Leave the tree open after `done` because Bevel does | DELTA: collapse unless the user had it open             |
| Answer as a child of the tree                       | Sibling below the thinking block (REQ-010)              |
| Two rows glowing                                    | Latest `in_progress` only (INV-002, INV-003)            |
| Chevron / tap on the live row                       | Live row is not a target (REQ-004)                      |
| Fade the whole tree on complete                     | One-frame snap on that row (REQ-005)                    |
| Hide that work happened when collapsed              | Duration header + chevron; SHOULD `"N steps"` (REQ-015) |

## Done

This skill is satisfied when every entry in `tests/spec/traceability.yaml`
has `status: passing`. A pretty screenshot is not done.

Name tests exactly as the yaml (`TestTurn_OnSend_ShowsThinkingShimmerAndStop`,
…). Prove each one red against the missing behavior, then green.

Non-goals: numeric progress, raw chain-of-thought as the primary surface,
restyling the composer / model picker except send ↔ stop.
