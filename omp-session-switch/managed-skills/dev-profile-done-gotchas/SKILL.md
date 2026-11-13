---
name: dev-profile-done-gotchas
description: "Use when wt done (alias for dev-profile-done) fails, hangs, or needs a fix, or when committing in a dev-profile worktree fails with sah-* command not found."
---

- `wt done` is a user alias: `~/.local/share/dev-profile/bin/dev-profile-done {{ args }}`. That path is the SAME file as `~/Developer/Personal/dev-profile/bin/dev-profile-done` (cp says "same file"), so merging to dev-profile main installs the fix. No profile.pkl/generate; `mise-tasks/generate` refuses. Edit the bin file directly.
- Fixture: `bash tests/done-fixture.sh <dir-containing-bin/dev-profile-done>` (pass `.` for a worktree). To prove RED, write `git show main:bin/dev-profile-done` into /tmp/x/bin/ (chmod +x) and pass /tmp/x. The edit tool can drop the exec bit: `chmod +x bin/dev-profile-done` or the fixture says "missing".
- Fixed 2026-11-09 (ecabc14): `free_name` now skips names with branches beneath them (`wip` vs `wip/foo` -> "cannot create refs/heads/wip"). Parked names: wip, wip-2, wip-3...
- Known open slowness: `stash_tree_blocked` runs one `git cat-file -s` per added/modified file. A stash with ~62k untracked files (eapp-system stash@{0}, agent worktree leftover) stalls the run >11 min. Fix is one `git cat-file --batch-check='%(objectsize)'` call. Rerun is resumable: a stash is dropped only after its wip commit exists. Don't kill mid-run unless needed; nothing is pushed until the stash phase ends.
- Committing in a dev-profile worktree: hk pre-commit needs `sah-*` tools; put `~/Developer/Software-Automation-Holdings/platform/.generated/bin` on PATH or the commit fails with exit 127. Then `wt merge -y main` from the worktree.
- `wt list` and dry-runs on big repos take 20s+ and background-promote; wait on the job, don't poll.
