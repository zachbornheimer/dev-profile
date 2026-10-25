---
name: babysit-pr
description: Drive a PR from opened to MERGED-verified — monitor CI inline, fix real failures, triage every review thread honestly, converge the adversarial reviewer round-by-round, hunt non-check merge blockers, arm auto-merge, and confirm the merge. Pair with /loop for continuous watching.
---

# Babysit PR

Own the full lifecycle: opened → checks green → threads resolved → review verdict
MERGE → auto-merge fires → **merged-verified**. The org ruleset blocks merge while
any review thread is open or CI is red. Drive to merged unattended — don't stop
and ask. Never bypass a gate; never claim merged without reading `state: MERGED`.

## Cardinal rules (each one is a real scar)

- **Watch checks INLINE — foreground loops only.** A background/detached monitor
  inside a subagent dies silently when the agent's turn ends (bit four agents on
  2026-07-30). One foreground bash loop, ~30s intervals, bounded per cycle.
- **Arm auto-merge first** (`ghx pr merge <n> --squash --auto`), then everything
  after is _unblocking_, not merging. At the end, poll `state`/`mergedAt` — armed
  - green can still sit; if it does, run the blocker hunt below.
- **Convergence is trustworthy; bypassing is forbidden.** An adversarial-review
  FIX-FIRST is a to-do list. Fix every concrete finding on its merits. A weak
  finding that points at real ambiguity → make the code unmistakable (a false
  positive is a code smell). A residual contradicting a PRIOR round's explicit
  ruling on unchanged code → post a factual PR comment quoting both rulings
  (gives convergence memory), keep going. Escalate to the owner ONLY for
  cross-repo work the PR can't contain or a reversal of an owner design decision.
  The sanctioned landing tool is `belt pr apply` (dev-config belt CLI) — always
  try it first. The owner's emergency instrument is `belt pr force-merge`
  (org-owner credential): scripted break-glass that temporarily unlocks ruleset
  18071128 in pull_request mode, merges, and GUARANTEES re-enable of the
  blocking (unconditional restore + verified end-state + audit record). There
  is NO standing `--admin` path; agents surface the command, never run it.
- **Threads: fix-or-rebut with evidence, never rubber-stamp.** Bot threads
  (sentry/Seer/Renovate/…) gate the merge and are right about half the time.
  Real → fix, push. False → reply with file:line evidence (for "X regressed"
  claims, compare against the legacy/baseline behavior side-by-side), THEN
  resolve via GraphQL `resolveReviewThread`. Resolving without a fix or a
  substantive reply is the sin.
- **Use `ghx` for ALL gh operations** — reads and mutations alike (identical args,
  rate-limit-pool aware, never stalls). No plain `gh`, no pr-merger.
- **Check for an existing PR before opening one** (`ghx pr list --state open`);
  nudge it, don't duplicate.

## The loop

**1. Checks.** `ghx pr checks <n>` / rollup poll until nothing pending.

- Failed → `ghx run view <id> --log-failed`, fix the real defect, push. Retry a
  flaky job once; a second identical failure is not flake — read it.
- CANCELLED is often concurrency debounce — confirm a newer run passed before
  treating as failure.
- A check failing on code your diff doesn't touch usually means a **stale
  branch** (e.g. CodeQL Analyze finding zero source) — merge the base forward.
- A provably broken gate (missing config, arch-crash, independent of your diff)
  may be routed around ONCE with the brokenness documented in the commit body —
  then fix the gate itself as follow-up. Never weaken a working gate.
- Generated-file conflicts (lockfiles, SDKs): regenerate with the toolchain,
  never hand-edit.

**2. `BLOCKED` with all checks green → hunt non-check blockers, in this order:**

1. **Unresolved review threads** (`required_review_thread_resolution`) — the
   most common invisible blocker; list via GraphQL `reviewThreads`.
2. Required approving review — read the ruleset's actual `pull_request` params
   (count is often 0 and something else is the blocker). You cannot approve
   your own PR; if a human approval is truly required, surface that one action.
3. Org-ruleset required workflows — verify the run exists on the CURRENT head.
4. Unsigned commits (`required_signatures`) — check `verification.verified`
   per commit via the API.

**3. Adversarial review rounds** (reviewed-class or similar): per the
convergence rule above. Re-trigger only legitimately (new commit, or rerun of
the run — never game re-rolls). Report each round's verdict + what you did.

**4. Merge confirmation.** Poll until `MERGED`; report the merge commit SHA.

**5. Report**: per failed check and per thread — what it was, fixed vs rebutted,
with the evidence; plus anything escalated and why.

## Tools of record

- Loop pattern for unattended watching:
  `/loop 5m babysit PR <n> on <org/repo> per the babysit-pr skill` (or
  `/schedule` for cloud).

## Hygiene (unchanged basics)

- **Draft = in progress; Ready = gates green.** `ghx pr ready` only with CI
  green, zero open threads, no conflicts.
- **Rebase conflicts:** `git fetch origin <base-ref>` then
  `wt step rebase origin/<base-ref>` → resolve →
  `git push --force-with-lease -u origin <branch>`.
- **Linear ticket:** In Progress at start; plan as brief bullets; In Review at
  ready; comment blockers — never silently stall.
- **Branch naming:** `<type>/<ticket-id>-<short-kebab-description>`.
- **Commit signing (mandatory):** commits must verify. Where local signing is
  configured (this Mac), `wt step commit` (signed via local git config; no
  `-m`); in environments without it, use `gh-commit` (web-flow signing):

  ```bash
  gh extension list | grep -q kassett/gh-commit || gh extension install kassett/gh-commit
  GH_REPO="<owner>/<repo>" gh commit -B <branch> -A -m "<type>(<scope>): <desc> (<ticket>)"
  git fetch origin <branch> && git reset --hard origin/<branch>
  ```
