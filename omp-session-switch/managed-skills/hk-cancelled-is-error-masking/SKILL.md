---
name: hk-cancelled-is-error-masking
description: "Diagnosing hk pre-push/pre-commit failures that report \"command was cancelled\" — the cancelled step is a sibling hk stopped, not the cause; where the real error lives and what authenticated fixes apply."
---

# hk "command was cancelled" is error masking, not the cause

When one step fails, hk cancels the steps still running and can report a *cancelled
sibling* as the hook error ("command was cancelled") instead of the step that
failed. Measured on oh-my-pi-ci 2026-11-03: five pre-push failures, each naming a
different harmless step (check-symlinks, check-executables-have-shebangs,
check-added-large-files, check-case-conflict) for one underlying failure.

## Where the real error lives

`<git-dir>/hk/output.log` — the failing command's own output. Read it before
believing the step hk printed. Also `<git-dir>/hk/hk.log` for the per-attempt
ERROR lines with timestamps. Worktrees keep these under
`<repo>/.git/worktrees/<name>/hk/`.

## Two confirmed real causes behind the mask

1. **pinact / zizmor 403**: both call the GitHub API unauthenticated (60 req/h
   per IP). A busy day exhausts the budget; every lookup 403s, the step fails,
   siblings report "cancelled". Fix: export `GITHUB_TOKEN` (from `gh auth token`)
   into the hook. Landed in `bin/dev-profile-pre-push` (dev-profile commit
   2afc700, 2026-11-09): the wrapper exports gh's token and prints
   `HK_OUTPUT_FILE` content on failure, naming this exact masking behavior.
2. **Missing `origin` remote / `origin/main` target** (foxguard-typescript in
   the oh-my-pi clone, which only has `fork` + `upstream`): see
   skill `omp-fork-push-hook-remotes`.

## Ambient factor

A heavily loaded host (~56 omp sessions, load 200-300, swap exhausted) makes every
gate step 10-30x slower and multiplies these failures — investigate under load
before trusting standalone "the named command passes in 0.4s" probes; the named
command was never the failure.
