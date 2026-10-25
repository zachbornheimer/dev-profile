---
name: agentmux-verify
description: Verify an agentmux change against the REAL running system and drive it to a proven-working end-state — mise run install, a FRESH process, observe the effect, and when verification reveals a defect, fix it at root and re-verify WITHOUT asking. Load before claiming any agentmux change works.
---

# agentmux-verify

Verification here is not a checkbox and not a question you bring back to Zach — it
is the loop that ends only when you have **observed the real end-state working on a
freshly-installed binary**. If verifying reveals a defect, you fix it at the root and
re-verify. You do not stop to ask permission for reversible work. Delivering the goal
is the job; "the test passes" and "it should work now" are not the goal.

## Why this skill exists (the recurring failure)

Changes get called "done" from green unit tests or a prior report, but the LIVE
TUI/CLI still shows old behavior — wrong aesthetics, no switch pulse, typing lag,
`chat/resume <provider>:<id>` failing. Two compounding causes, every time:

1. **Stale process.** `agentmux node`/`runner`/`chat` processes are mapped to an OLD
   binary on an OLD inode. Rebuilding does NOT change a running process. Looking at a
   chat that was already open (even after an install) verifies the OLD code. The
   binary on disk being fresh is not enough — the _process you observe_ must have been
   started AFTER the install.
2. **Wrong evidence.** `go test` proves a code path, not the live surface. A grep for
   a process name or an event type is a proxy, not the claim. Asserting a proxy as
   fact ("no runner running", "0 heartbeats") is how you ship a false "done."

## The loop (do not exit until the end-state is observed green)

1. **Install.** `mise run install`. Confirm `~/.local/bin/agentmux version` == current
   HEAD short-sha. (The disk binary may already be current — that is NOT verification.)
2. **Drive a FRESH process** started after the install — never a reused one:
   - Functional, automated: `mise run verify-tasks` (the harness installs + drives
     fresh throwaway processes against staged fixtures and asserts per-task claims).
   - Eyes-on aesthetics/behavior: a NEW `tmux new-session … '~/.local/bin/agentmux
     chat <job>'` → `capture-pane -e -p` → `freeze` → READ the png. Or run the CLI
     command directly and read its real output.
3. **Observe the real end-state**, not a proxy. Durable proof: the actual effect, on
   the real system, end-to-end, sustained where it matters (a pulse that fires, a
   resolver that returns the job, a strip that has a blank line above it). Interactive
   things (switch pulse, typing latency, hop, streaming, `provider:id` resolution)
   CANNOT be proven by a test — reproduce them on the fresh binary.
4. **If it's wrong, fix the root and loop.** A defect surfaced by verification is
   yours to fix now: red-first test that captures it, root-cause fix (not a
   symptom-patch), `mise run install`, re-observe. Repeat until observed green. Do not
   report the defect and stop; do not ask whether to fix reversible work.
5. **State the claim with its evidence and limits.** "Installed <sha>, ran
   `agentmux chat claude:<id>` on the fresh binary, it resolved to job <x> and opened"
   — or "unit-verified; live NOT yet confirmed, driving it next." Never "should work."

## Autonomy (this is the point — stop asking)

- Verification revealing a bug is a mandate to fix it, not a fork to escalate. Fix it,
  verify it, report the outcome. Pause ONLY for a genuine fork: destructive/irreversible
  action, a real scope change, or input only Zach can give. "Should I fix this obviously-
  broken thing / should I verify?" is not a fork.
- Route the code fix through prompt-writer → implement (worktree); you keep the LIVE
  verification — install the result and observe it yourself before calling it done.
- On agentmux specifically: if the repo has a concurrent run pushing to main, fetch
  before every push and integrate rebase + ff-only (merges are blocked) — coordinate,
  don't clobber; but that is the only reason to slow down, not a reason to ask before
  fixing a disjoint bug.

## Don'ts

- Don't `go build`/`go test` and then look at an already-open chat — that's the bug.
- Don't infer visual/interactive behavior from a passing test.
- Don't trust another agent's "it works", a screenshot on an unknown binary, or your
  own memory — check the installed sha and drive a fresh process yourself.
- Don't diagnose from a grep/process-name and assert it as fact — verify the end-state.
- Don't bring "want me to fix it?" back to Zach for reversible work — fix it and report.

## Checklist before saying done / working / fixed

- [ ] `mise run install` ran; `agentmux version` == current HEAD sha
- [ ] The process/CLI run I observed was started AFTER that install
- [ ] Functional: `mise run verify-tasks` gate PASS (or a fresh unit + fresh render)
- [ ] Interactive/visual claim (pulse, typing, hop, `provider:id`): reproduced on the
      fresh binary, not inferred
- [ ] Any defect verification surfaced was fixed at root + re-verified, not just filed
- [ ] Claim states its evidence and its limits
