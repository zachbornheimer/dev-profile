---
name: landing-dev-env-changes
description: "Land changes to Zach's dev-env repo (and home-dir config like ~/.config/zsh, ~/.ssh/config) so they are actually pushed: wt merge only lands on local main; origin/main needs a PR."
---

# Landing dev-env changes (verified 2026-11-09)

1. Work in a worktree: `wt switch -c <type>/<slug> --no-cd`, edit under `~/Developer/Personal/.worktrees/dev-env-<type>-<slug>/`.
2. `git add -A && git commit` (hk hooks run; conventional-commit subject <=60 chars). `wt step commit` also works but strips exec bits only if the file mode was dropped by a rewrite: check `git ls-tree HEAD <script>` shows 100755 for tools/vps/*.sh and recommit with chmod if not.
3. `wt merge -y main` lands on LOCAL main only. It does NOT push.
4. `git push origin main` is refused by a policy hook ("Open a PR with wt pr"). Instead: `git push origin main:refs/heads/<branch>` then `gh pr create --repo zachbornheimer/dev-env --base main --head <branch> ...`. Never claim "pushed" before `git fetch && git log origin/main..main` is empty or a PR exists.
5. Home-dir edits (`~/.config/zsh/*`) are committed with `mise dot save && mise dot sync` (history repo `~/.local/state/mise/history/repo.git`). `~/.ssh/config` is NOT tracked by `mise dot`; say so instead of claiming it is committed.

## Test gotchas
- Tests that run `tools/vps/provision-marker.sh` must set `PATH=/usr/bin:/bin:/usr/sbin:/sbin`; a mise shim ahead of /usr/bin reads untrusted `~/.config/mise/config.local.toml` and fails.
- `mise run lint`/`ci` on darwin/arm64 fail installing `aqua:denisidoro/navi` and `aqua:upx/upx` (linux-only); use `MISE_AUTO_INSTALL=false mise tasks deps ci` / `mise run -n ci` to check the graph.
- Commands over ~20s get promoted to background jobs; use `wait` with job_id then read the log_path.
