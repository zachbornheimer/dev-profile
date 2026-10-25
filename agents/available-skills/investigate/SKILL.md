---
name: investigate
description: Use when answering "how does X work", "where does Y come from", or "why does Z behave this way" about an unfamiliar system — and a wrong answer is costly. Also load when you catch yourself guessing without direct evidence.
---

# Investigate

Turns a factual question about how a system actually behaves into an evidence-backed
answer with a stated confidence level. The discipline: evidence before conclusion,
never after.

## The failure mode this corrects

The default failure is **believing a plausible story instead of verifying it.**
Three faces — all feel like progress, all produce wrong answers:

**1. Single-source belief.** The first hit looks right, so you stop.
One source is a hypothesis. Two agreeing, independent sources is a finding.
Never build on one.

**2. Coincidental-match false positives.** A weak signal mistaken for proof.

> Real case: `grep` for the first 8 chars of a UUID "found" it in a 1–3 GB SQLite
> file — looked like proof the session was stored there. Full-UUID grep returned
> zero. The 8-char hit was a random collision. Lesson: size the signal; match the
> full identifier, not a prefix.

**3. Category confusion.** Two things share a shape; the wrong one is assumed.

> Real case: The user's "session ID" (copied from the tool UI "Get request ID")
> never resolved in storage — because a **request ID** (one generation) and a
> **composer ID** (the whole conversation) are different categories that both look
> like UUIDs. Named category > shape alone. Lesson: confirm the semantic type before
> querying, not after.

## The 5-step method

**Step 1 — Restate as a falsifiable claim.**
"X is stored at path P in format F" — not "how does X work." A claim you can prove
or disprove. Vague questions produce vague, unfalsifiable answers.

**Step 2 — Gather evidence from the system itself.**
The actual file, DB row, query plan, log line, or running output. Never from memory
or assumption. The system is the source of truth; everything else is a prior.

**Step 3 — Cross-check a second, independent source.**
A reference implementation, official docs, or a second probe that would fail if the
first were a fluke.

> Real case: Naive scan (every record, searching for a title) took 68s. The reference
> implementation revealed a clean JSONL index file — lookup was instant. The second
> source exposed a better path that reverse-engineering alone never would have found.

**Step 4 — Size the signal. Ask "could this be coincidence?"**
Before calling something "found": full string > prefix match; exact key > substring;
typed field > shape-guess. Ask: "Would this match if my claim were false?" If yes,
it's not evidence.

**Step 5 — Report: answer + evidence + confidence + gaps.**
State the conclusion. Cite exactly what you observed (tool result, line number, field
value). Attach a confidence level: **high** (two independent sources, no gaps),
**medium** (one direct source, minor gaps), **low** (inference only). Explicitly list
what you could NOT confirm. A claim without its evidence is a guess in a lab coat.

## When NOT to use this (use these instead)

| Need                                                   | Use instead                                                                                        |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| Find code in the codebase (a pointer, not methodology) | `explore` / `codebase-explorer` — workers that return references; this skill decides what to trust |
| Fix a bug                                              | `debug-protocol` — structured fault isolation for broken behavior                                  |
| Research via the web                                   | `deep-research` — web-first, citation-driven, multi-source synthesis                               |
| Prove a change worked                                  | `verify` — post-change end-state confirmation against a specific claim                             |
| Validate a number going to a client                    | `verifiable` — client-facing evidence standard, higher bar                                         |

This skill is the **methodology layer** — it governs when to believe a finding and
what to say. The workers above produce the raw evidence; this discipline tells you
how to evaluate it.
