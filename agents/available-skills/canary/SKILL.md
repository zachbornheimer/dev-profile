---
name: canary
description: Use when the user says "canary", "use this as a canary", "good canary", or "don't fix that yet". A real failing prompt that proves a system change. Do not use for deploy canaries.
---

# Canary

A canary is a real case that fails the way he cares about. It is not a toy fixture, and it is not a deploy canary (`deploy`).

These gotchas are from his prompts in September and October 2026. `self-improve` should keep them.

## Gotchas

1. **"Don't fix that yet" means leave the symptom.** "it's a good canary for our skill" means the broken case stays until the skill or hook catches it. Patching the example hides the canary.

2. **"Use this as a canary to fix and apply" means change the system, then re-run this prompt.** Done is the canary output matching the expected observable. A unit test that restates the wish is not the canary.

3. **The case is real.** zq purge stalling before any output, a visual mismatch against a known-good page, or a prompt that injected one skill when it should have injected several. Copy his words. Do not invent a cleaner example.

4. **Do not mix this with a deploy canary.** Shipping, error rate, and rollback belong to `deploy`.

## Procedure

1. Copy the prompt or case verbatim.
2. Write the expected observable in one line, and the current failure in one line.
3. If he said don't fix yet, stop.
4. If he said fix and apply, change the system that should have produced the observable. Do not patch the example.
5. Re-run the canary. Report pass or fail with the output.
