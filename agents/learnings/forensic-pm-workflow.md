# Two-Stage Forensic Assessor → PM Workflow Spec

Accepted 2026-10-30. Replaces the single-agent Mastra `learn-from-transcript` ticket-dump flow.

## User's Core Principles (Verbatim Intent)

- "The thing is we need to address wall time and token usage - not just the failure of listening. Frustration means the whole session needs deep analysis for token savings and walltime. I wouldn't be frustrated if a session was 2 min."
- "`atask` is supposed to be a tool for an agent to use to make sure what they think is done is actually done verifiably. It's not supposed to be this magic system. It serves a narrow purpose."
- "So I'd like for us to establish a workflow. Doing it like we did: the first prompt then queueing the second. Then from there, we want to start a new agent that gets the entire conversation from the first as input with mcp access."
- "For turns, i would think we should have the agent prompt and then we should inject the entire conversation instead of having a read (im pretty sure that's more token efficient)."
- "for that agent, i want to turn on `--advisor` and then do the same `/queue` prompt thing where we ask 'are you happy with this? also check adversarially.'"

## Intake Triggers

1. **Real-Time Frustration Trigger (`frustration-learn.py`):** Fires when `prompt_answers` (`jev`) scores `Frustrated >= 0.7` or lexical/transcript signals cross threshold (`>= 3`).
2. **Daily Triage Trigger (`jev` Worst 3–5):** Pre-filters the day's sessions by deterministic waste metrics (active wall time, mega-turns, `tool_error` count, `correction` turns, model switches, USD/token burn) and uses `jev` to select the worst 3–5 sessions (if any).

## Stage 1: Forensic Assessor (`omp --model @slow`)

- **Model:** `@slow` (`google-antigravity/gemini-4-argon:auto` with fallback chain)
- **Environment:** `LEARNER=1`, `AGENTMUX_NESTED_RUN=1`
- **Pass 1 Prompt:** `@<handoff-dir>/<timestamp>-omp-<session_id>-slow.prompt.md` (`src/workflows/learn-from-transcript/analyze.yaml` with `{path}` replaced by `~/.local/share/capability-replicas/annotated/<conversation>.annotated.json`).
- **Pass 2 Queued Follow-Up (`/queue`):**
  ```text
  /queue I feel like your answer is superficial. For example, you didn't try and identify root causes.
  ```
- **Output:** Complete 2-pass forensic conversation (exact wall-time and token accounting across models/phases, 5-whys code-verified root causes at `file:line`, disproof of false agent claims, `ForensicsReport` JSON, and competing Option A vs. Option B fixes with measured savings).

## Stage 2: Forensic PM Agent (`omp --model @slow --advisor`)

- **Model & Flags:** `omp --model @slow --advisor` (`Gemini 4 Argon` + Advisor runtime enabled)
- **Environment:** `LEARNER=1`, `AGENTMUX_NESTED_RUN=1`, MCP access (`capability` + `linear-personal`)
- **Pass 1 Prompt (Single-Prefill Inline Injection):**
  `@<handoff-dir>/<timestamp>-pm-<session_id>.prompt.md` containing:
  1. `/Users/zbornheimer/.agents/learnings/pm-agent-prompt.md`
  2. `<stage1_forensics_conversation>` with the entire Stage 1 conversation injected inline (avoiding multi-turn chunked file reads so the entire conversation lands in the prompt cache on Turn 1).
- **Pass 2 Queued Follow-Up (`/queue`):**
  ```text
  /queue are you happy with this? also check adversarially.
  ```
- **Output:**
  1. Workspace lock verification (**Linear Personal** for `~/Developer/Personal/*` and `~/.agents/*`).
  2. Deduplication & Pain-Ledger compounding on existing open Linear issues (with read-back `updatedAt`).
  3. Parent (Root-Cause Chain) + Atomic Child Sub-Issues (`parentId`, `blockedBy`) triaged into **Lane 1 (`Ready to Execute`)**, **Lane 2 (`Experiment Needed`)**, and **Lane 3 (`Backlog`)**.
  4. Ranked **Top 3 Ready-to-Execute Dispatch Queue** with exact `--proof` and `--regression` commands for Stage 3 worker execution (without polluting `atask` during PM triage).
