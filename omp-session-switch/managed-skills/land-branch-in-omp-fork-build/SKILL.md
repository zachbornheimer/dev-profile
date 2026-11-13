---
name: land-branch-in-omp-fork-build
description: How to land a feature or fix branch into the active local `omp` binary and the fork's ephemeral `omp-build` CI pipeline.
---

# Landing a Branch in the `oh-my-pi` Fork Build

1. **Create a topic branch off `upstream/main` (or `origin/main`):**
   - Never commit or cherry-pick directly onto `assembled` or `omp-build` (`main-branch-guard.py`, `.git/hooks/reference-transaction`, and `omp-build.yml` reject non-merge commits on `assembled`).
   - Push the topic branch to `origin`: `git push origin HEAD:refs/heads/feat/<slug>`.
2. **Register `.omp-build/branches/feat/<slug>.toml` on `zachbornheimer/oh-my-pi:main`:**
   - Include `reason`, `upstream = "no" | "candidate" | "submitted"` (plus `pr = "..."` when `submitted`), and `layer = 50` (do not include a `branch` key; the path under `.omp-build/branches/` is the branch name).
   - Verify with `bash ~/.agents/available-skills/updating-oh-my-pi/scripts/probe-build.sh --repo ~/Developer/Personal/oh-my-pi --base refs/remotes/origin/main --add feat/<slug>`.
   - Land the `.toml` file on `zachbornheimer/oh-my-pi:main` via a small PR.
3. **Cross-branch conflict resolution:**
   - Do not merge topic branch A into topic branch B (which contaminates B's upstream PR diff).
   - Use `.omp-build/rr-cache` (`git config rerere.enabled true` + `git merge --no-ff --no-edit --rerere-autoupdate` in `omp-build.yml`) for textual conflicts and `.omp-build/merge-fix/<branch>.patch` for semantic-only conflicts.
