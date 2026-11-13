---
name: isa-platform-sdk-conformance-triage
description: "Triage a failing sdk workflow conformance job (live matrix) in isa-platform: reading the matrix, golden refresh, and repo-specific gotchas that cost time."
---

Short-term bridge; a workflow/tool should own the golden-refresh sequence.

## Reading the failure
- Job `conformance`, step "Run live conformance matrix" (`tests/conformance/run-all.sh`, push-to-main and dispatch only; PRs run mock-only).
- The long "Deferred surfaces" table is informational allowlist (legend: NOT a failure). The failure is a `FAIL`/`MISSING` cell in the matrix table. Language columns FAIL = cross-language divergence; only the Golden column FAIL with all languages PASS = golden lags the live engine.
- Detail: download artifact `sdk-conformance-results` from the run (`gh run download <id> -n sdk-conformance-results`), read `results/golden-diffs.md` and `results/cross-language-diffs.md`. Re-run offline: copy `tests/conformance` to a temp dir, put the artifact at `results/`, run `python3 tools/diff_results.py` (needs pyyaml; exit 0 = green).
- Golden refresh per README: copy `results/python/<op>.<persona>.json` over `goldens/<op>.<persona>.test.json`. Live key: `aws secretsmanager get-secret-value --secret-id isaapi/conformance/test-key`; base URL https://zyins.isaapi.com. Measured 2026-11-05: JSON key order of the request body did NOT change the live answer.

## Repo gotchas
- `wt tree-for-changes` stashes a dirty main checkout (it took 13 uncommitted files and left a conflicted stray worktree). Use `wt switch --create <type/slug> --base origin/main --no-cd` instead; verify `git status --short | wc -l` unchanged.
- hk commit-msg hook requires subject `type(scope): description`; a leading Linear id ("SAH-123 fix(...)") is rejected. Put the ticket in the body; the PR title may carry it.
- Pre-push runs the full contract suite (~15 min). Run push in the background with output to a file.
- Cursor agents open duplicate PRs for the same failure (#754/#755; golden refresh #756 beat my #758, which became an empty commit). Before writing a fix, list open PRs and recent main commits touching `tests/conformance/goldens/`.
- A main commit with no changes under conformance paths skips the `conformance` job; it is not acceptance evidence. Cite the run whose conformance job is SUCCESS.
- `go` from PATH may be 1.27 while go.mod toolchain is 1.26.3: set GOROOT to the mise 1.26.3 install. `gh` calls hung intermittently on 2026-11-09; wrap in `timeout`.
- Merge queue: `gh pr merge <n> --squash --auto` is refused ("strategy set by merge queue") but still enqueues; check mergeQueueEntry via graphql.
