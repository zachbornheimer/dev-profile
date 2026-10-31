---
name: pin-landing-policy
description: "Pin a decision only when the user alone holds the call; land reachable work yourself instead of pinning a go-ahead"
condition: "(?i)\\b(pin|pinning|decision)\\b"
scope: "text"
---

Pinning is not a way to delay or hand off work. Finish every action that does not depend on the answer first, then pin only the remainder. Decide anything the code, the config, the docs, or the user's earlier words already answer: never pin a go-ahead for work you were already asked to do.

When your reasoning concludes an action is safe, verifiable, and reversible, take that action. Do not re-derive a fork from a step you already concluded is fine. If a merge is blocked by dirty files, back them up, rebase your branch onto only its own files, fast-forward, and hash-verify; do not pin to ask whether to proceed with work already in motion.

Never pin a question a prior user message already answers. Reread the last user messages and the task handoff before pinning: if any of them names the choice, act on it and report.
