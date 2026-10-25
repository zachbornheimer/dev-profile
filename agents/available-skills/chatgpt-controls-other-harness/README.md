# chatgpt-control-claude

Bootstrap repo for the working ChatGPT → local runner → Claude Code/repo → evidence ZIP loop.

> **Executor terminology:** this project drives **Claude Code by Anthropic** through the local `claude` command. The repository name remains `chatgpt-control-claude`.

Intended local path:

```text
/Users/zbornheimer/Developer/Personal/chatgpt-control-claude
```

A small, explicit protocol for a cloud planner/reviewer (for example ChatGPT) to hand work to a local machine, receive deterministic evidence, and continue the loop.

This repository is intentionally **not** a full orchestration framework. It standardizes the bootstrap seam:

```text
cloud planner/reviewer
        ↓
one fresh run-<uuid>.py artifact
        ↓
local controller downloads + runs it synchronously
        ↓
runner mutates/inspects the real local repo
        ↓
runner ALWAYS emits ~/Downloads/<uuid>.zip
        ↓
controller attaches ZIP to the same chat
        ↓
cloud reviewer audits evidence
        ↓
fresh runner or terminal result
```

The important property is that the coding-agent summary is never treated as proof. The evidence bundle is the proof surface.

## What is in this starter

- `AGENT_CONTRACT.md` — the rules to give the cloud agent that emits runners.
- `SPEC.md` — protocol, state machine, invariants, and failure semantics.
- `PROMPT_FORMAT.md` — a concrete planner→runner request format.
- `EVIDENCE_SCHEMA.md` — required ZIP contents and report semantics.
- `OPERATIONS.md` — controller behavior, retries, races, troubleshooting.
- `schemas/` — JSON Schemas for request/report metadata.
- `examples/` — example request/report/planner message.
- `src/chatgpt_control_claude/` — tiny stdlib-only helper library and CLI.
- `templates/standalone_runner.py` — a self-contained runner scaffold.
- `controller/README.md` — how the UI/controller side should behave.
- `tests/` — protocol helper tests.

## Fast setup

After unzipping directly into that repository:

```bash
uv sync
uv run ccc new-uuid
uv run ccc scaffold
uv run python -m unittest discover -s tests -v
```

The generated runner is intentionally self-contained. A downloaded runner should not depend on this repository being importable.

## Recommended cloud-agent instruction

Give the agent `AGENT_CONTRACT.md` plus the task-specific request. The agent should return **one downloadable runner file only** when the controller loop is active.

The most important rules are:

1. Every emitted runner gets a **fresh UUID**.
2. One assistant turn exposes **one runner artifact**, not several downloadables.
3. The runner executes synchronously and all waits are bounded.
4. The runner never silently commits, pushes, merges, resets, or cleans.
5. Internal task failure is recorded in `report.json`; the runner process itself exits `0` so the controller can still return evidence.
6. The runner always attempts to create `~/Downloads/<uuid>.zip`.
7. Evidence is independent of model prose.
8. Re-running the same UUID is forbidden.
9. Controller fallback ZIPs are transport/controller evidence, not proof that the runner ran.
10. After a ZIP is sent back to chat, the controller pauses before looking for the next runner.

## Why the UUID is part of the protocol

The UUID is the correlation key for:

- runner filename: `run-<uuid>.py`
- evidence ZIP: `<uuid>.zip`
- local run/evidence directory
- deduplication
- controller state
- chat turn correlation

Never recycle an old UUID merely because the runner contents are the same. If you need the same runner again, copy it and replace the UUID everywhere.

## Default safety posture

Unless the human explicitly asks otherwise, generated runners should:

- preserve existing uncommitted work;
- avoid `git commit`, `push`, `merge`, `reset`, and `clean`;
- avoid destructive/shared-system changes;
- use bounded subprocess timeouts;
- record before/after Git state;
- package evidence even on failure;
- avoid uploading credentials/secrets into evidence.

## Relationship to a future real orchestrator

This is a bootstrap protocol. It is designed so the same concepts can later become first-class domain objects:

```text
Request
Run
Attempt
Command
Artifact
Evidence
Verification
Outcome
```

The controller is transport. The runner is a bounded local executor. The cloud agent is planner/reviewer. None of those should own the others' truth.
