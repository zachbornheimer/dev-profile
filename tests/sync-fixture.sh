#!/usr/bin/env bash
# `wt sync`, `wt reconcile` and `wt prune` across two clones of one repo: what
# reaches GitHub, what is reconciled or backed up, what is left untouched, and
# what cleanup removes. Real git and a real bare origin; gh and wt are stubs.
# Usage: sync-fixture.sh <generated-dir>
set -euo pipefail
export HK=0 # no global git hooks inside the fixture repos

out="${1:?usage: sync-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
sync="${out}/bin/dev-profile-sync"
reconcile="${out}/bin/dev-profile-reconcile"
prune="${out}/bin/dev-profile-prune"

fail() {
	echo "FAIL sync fixture: $*" >&2
	exit 1
}

# Identity for every repo here, without touching the user's config.
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false

commit() { # <repo> <file> <content>
	printf '%s\n' "$3" >"$1/$2"
	git -C "$1" add "$2"
	git -C "$1" commit -q -m "$2: $3"
}
on_origin() { git -C "${work}/origin.git" rev-parse --verify --quiet "refs/heads/$1"; }
backup_ref() { # <suffix>: this fixture's backup ref name for a clone, by suffix
	git -C "${work}/origin.git" for-each-ref --format='%(refname:short)' "refs/heads/backup/" | grep -E "^backup/[^/]+/$1\$" | head -n 1
}

git init -q --bare --initial-branch=main "${work}/origin.git"
git clone -q "${work}/origin.git" "${work}/seed" 2>/dev/null
git -C "${work}/seed" switch -q -c main
commit "${work}/seed" base.txt base
for branch in shared clash rebased; do
	git -C "${work}/seed" switch -q -c "${branch}" main
	commit "${work}/seed" "${branch}.txt" base
done
git -C "${work}/seed" push -q origin main shared clash rebased
git -C "${work}/origin.git" symbolic-ref HEAD refs/heads/main
for clone in a b; do
	git clone -q "${work}/origin.git" "${work}/${clone}" 2>/dev/null
	git -C "${work}/${clone}" remote set-head origin main
	git -C "${work}/${clone}" branch -q shared origin/shared
	git -C "${work}/${clone}" branch -q clash origin/clash
	git -C "${work}/${clone}" branch -q rebased origin/rebased
done

# GitHub moves on before clone a syncs: main gains a change that clone a also
# makes on its own branch, the fixture's `rebased` branch is rebased onto main
# (replacing only that test branch), and a PR head exists only as refs/pull/5/head.
git -C "${work}/seed" switch -q main
commit "${work}/seed" squash.txt s
git -C "${work}/seed" push -q origin main
git -C "${work}/seed" switch -q rebased
git -C "${work}/seed" rebase -q main >/dev/null
git -C "${work}/seed" push -q origin +refs/heads/rebased:refs/heads/rebased
git -C "${work}/seed" switch -q -c pr-only main
commit "${work}/seed" pr.txt p
git -C "${work}/seed" push -q origin HEAD:refs/pull/5/head
git -C "${work}/a" switch -q -c squashed main
commit "${work}/a" squash.txt s
git -C "${work}/a" fetch -q origin refs/pull/5/head
git -C "${work}/a" branch -q pr-5-head FETCH_HEAD

# Clone a: a new branch, and new commits on two shared branches.
git -C "${work}/a" remote add gone "${work}/missing.git" # a dead extra remote must not stop sync
git -C "${work}/a" switch -q -c feat/a main
commit "${work}/a" a.txt a
git -C "${work}/a" switch -q shared && commit "${work}/a" from-a.txt a
git -C "${work}/a" switch -q clash && commit "${work}/a" clash.txt a
git -C "${work}/a" switch -q main
(cd "${work}/a" && "${sync}") >/dev/null || fail "a clean clone must sync"
on_origin feat/a >/dev/null || fail "a new branch must reach GitHub"
on_origin squashed >/dev/null && fail "a branch whose content main already holds must not be pushed"
on_origin pr-5-head >/dev/null && fail "a branch GitHub holds as a PR head must not be pushed"
[[ "$(on_origin shared)" == "$(git -C "${work}/a" rev-parse shared)" ]] || fail "a fast-forward must be pushed"

# Clone b: the same shared branches moved differently, plus every kind of
# unique local state.
git -C "${work}/b" switch -q shared && commit "${work}/b" from-b.txt b
git -C "${work}/b" switch -q clash && commit "${work}/b" clash.txt b
git -C "${work}/b" switch -q main
commit "${work}/b" main-only.txt b
commit "${work}/b" tracked.bin small
printf 'stashed\n' >"${work}/b/stash.txt"
git -C "${work}/b" stash push -q -u -m keep
head -c 2097152 /dev/zero >"${work}/b/tracked.bin" # a tracked file grown past the limit
printf 'edited\n' >"${work}/b/base.txt"
printf 'new\n' >"${work}/b/untracked.txt"
head -c 2097152 /dev/zero >"${work}/b/big.bin"
status_before="$(git -C "${work}/b" status --porcelain)"
clash_before="$(git -C "${work}/b" rev-parse clash)"

code=0
(cd "${work}/b" && DEV_PROFILE_SYNC_MAX_FILE_MB=1 "${sync}") >"${work}/b.out" 2>&1 || code=$?
[[ "${code}" -eq 1 ]] || fail "an unresolved conflict must exit 1, got ${code}: $(cat "${work}/b.out")"

git -C "${work}/origin.git" cat-file -e "$(on_origin shared):from-a.txt" || fail "reconcile must keep the other clone's commits"
git -C "${work}/origin.git" cat-file -e "$(on_origin shared):from-b.txt" || fail "reconcile must add this clone's commits"
grep -q 'reconciled  *shared' "${work}/b.out" || fail "a clean rebase must report reconciled"

[[ "$(git -C "${work}/b" rev-parse clash)" == "${clash_before}" ]] || fail "a conflicting branch must stay as it was"
[[ "$(git -C "${work}/origin.git" rev-parse "$(backup_ref clash)")" == "${clash_before}" ]] || fail "a conflicting branch must be backed up"
grep -q 'wt reconcile clash' "${work}/b.out" || fail "a conflict must say how to resolve it"
grep -q 'were left out' "${work}/b.out" || fail "left-out files must be called out at the end"
grep -q 'Everything unique' "${work}/b.out" && fail "sync must not claim completeness while files are left out"
[[ "$(git -C "${work}/origin.git" show "$(backup_ref wip/main):tracked.bin")" == small ]] ||
	fail "an oversized tracked file must keep its committed version, not read as deleted"
clone_id="$(git -C "${work}/b" config dev-profile.sync-clone)"
[[ -n "${clone_id}" && "$(backup_ref wip/main)" == "backup/${clone_id}/wip/main" ]] ||
	fail "the clone id must be stored in the clone's config and name its backups"
[[ -z "$(backup_ref rebased)" ]] || fail "an older copy of a branch rebased on GitHub is not a conflict"
grep -q 'conflict  *rebased' "${work}/b.out" && fail "an older copy of a rebased branch must not report a conflict"
grep -q 'skipped  *.*big.bin' "${work}/b.out" || fail "a file over the size limit must be reported as skipped"
git -C "${work}/origin.git" cat-file -e "$(backup_ref wip/main):big.bin" 2>/dev/null && fail "a file over the size limit must be left out of the backup"

wip="$(backup_ref wip/main)"
[[ -n "${wip}" ]] || fail "uncommitted changes must be backed up"
git -C "${work}/origin.git" cat-file -e "${wip}:untracked.txt" || fail "the backup must hold untracked files"
[[ "$(git -C "${work}/origin.git" show "${wip}:base.txt")" == edited ]] || fail "the backup must hold modified files"
[[ "$(git -C "${work}/b" status --porcelain)" == "${status_before}" ]] || fail "sync must leave the worktree as it was"
[[ "$(git -C "${work}/b" stash list | wc -l | tr -d ' ')" -eq 1 ]] || fail "sync must leave stashes in place"

[[ "$(git -C "${work}/origin.git" rev-parse "$(backup_ref main)")" == "$(git -C "${work}/b" rev-parse main)" ]] ||
	fail "commits on main that GitHub lacks must be backed up"
stash="$(git -C "${work}/b" rev-parse 'stash@{0}')"
[[ -n "$(backup_ref "stash-${stash:0:12}")" ]] || fail "a stash must be backed up"

# Another clone restores the stash straight from GitHub.
git -C "${work}/a" fetch -q origin
git -C "${work}/a" stash apply -q "origin/$(backup_ref "stash-${stash:0:12}")" || fail "a backed-up stash must apply in another clone"
[[ -f "${work}/a/stash.txt" ]] || fail "the applied stash must restore its files"
rm "${work}/a/stash.txt"

# A second run pushes nothing new; the conflict still stands.
(cd "${work}/b" && DEV_PROFILE_SYNC_MAX_FILE_MB=1 "${sync}") >"${work}/b2.out" 2>&1 || true
grep -qE '^  (pushed|backed-up|reconciled) ' "${work}/b2.out" && fail "a second sync must push nothing: $(cat "${work}/b2.out")"

# --dry-run pushes nothing.
git -C "${work}/a" switch -q -c feat/dry main && commit "${work}/a" dry.txt dry && git -C "${work}/a" switch -q main
(cd "${work}/a" && "${sync}" --dry-run) >"${work}/dry.out" || fail "sync --dry-run must succeed"
grep -q "would push  *feat/dry" "${work}/dry.out" || fail "a dry run must say what it would push"
grep -q "Dry run: nothing pushed" "${work}/dry.out" || fail "a dry run must not claim a backup"
on_origin feat/dry >/dev/null && fail "sync --dry-run must not push"

# wt reconcile stops mid-rebase on a conflict, and pushes once it is resolved.
git -C "${work}/b" worktree add -q "${work}/b-clash" clash
code=0
(cd "${work}/b-clash" && "${reconcile}") >/dev/null 2>&1 || code=$?
[[ "${code}" -eq 1 ]] || fail "reconcile must stop on a conflict"
[[ -d "$(git -C "${work}/b-clash" rev-parse --git-path rebase-merge)" ]] || fail "reconcile must leave the rebase for a person"
printf 'merged\n' >"${work}/b-clash/clash.txt"
git -C "${work}/b-clash" add clash.txt
GIT_EDITOR=true git -C "${work}/b-clash" rebase --continue >/dev/null 2>&1
(cd "${work}/b" && "${sync}") >/dev/null 2>&1 || true
[[ "$(git -C "${work}/origin.git" show clash:clash.txt)" == merged ]] || fail "the resolved branch must reach GitHub"

# A bare clone with a linked worktree: the bare entry has no HEAD to back up.
git clone -q --bare "${work}/origin.git" "${work}/c.git"
git -C "${work}/c.git" worktree add -q "${work}/c-main" main
(cd "${work}/c-main" && "${sync}") >"${work}/c.out" 2>&1 || fail "a bare clone's worktree must sync: $(cat "${work}/c.out")"

# A left-out file alone is enough to withhold "everything is on GitHub".
head -c 2097152 /dev/zero >"${work}/c-main/huge.bin"
code=0
(cd "${work}/c-main" && DEV_PROFILE_SYNC_MAX_FILE_MB=1 "${sync}") >"${work}/c2.out" 2>&1 || code=$?
[[ "${code}" -eq 1 ]] || fail "a left-out file must make sync exit 1"
grep -q 'Everything unique' "${work}/c2.out" && fail "sync must not claim completeness while a file is left out"
rm "${work}/c-main/huge.bin"

# A clone whose pre-push checks refuse everything: publishing under a branch's
# own name is refused, but the work still reaches GitHub as a backup.
git clone -q "${work}/origin.git" "${work}/d" 2>/dev/null
git -C "${work}/d" remote set-head origin main
git -C "${work}/d" config hook.gate.event pre-push
git -C "${work}/d" config hook.gate.command 'echo "checks failed" >&2; exit 1'
git -C "${work}/d" switch -q -c feat/gated main
commit "${work}/d" gated.txt g
(cd "${work}/d" && "${sync}") >"${work}/d.out" 2>&1 || fail "work preserved as a backup must not fail sync: $(cat "${work}/d.out")"
on_origin feat/gated >/dev/null && fail "a branch the pre-push checks refuse must not be published under its own name"
[[ "$(git -C "${work}/origin.git" rev-parse "$(backup_ref feat/gated)")" == "$(git -C "${work}/d" rev-parse feat/gated)" ]] ||
	fail "a branch the pre-push checks refuse must be preserved as a backup"
grep -q 'gated  *feat/gated' "${work}/d.out" || fail "a refused branch must be reported"

# --- prune: gh and wt are stubs; deletions on origin are real.
stubs="${work}/stubs"
mkdir -p "${stubs}"
export PRUNE_LOG="${work}/prune.log" PRUNE_OPEN="${work}/open"
cat >"${stubs}/gh" <<'GH'
#!/usr/bin/env bash
case "$*" in
"repo view --json owner,defaultBranchRef") echo '{"owner":{"login":"me"},"defaultBranchRef":{"name":"main"}}' ;;
"pr list --state merged"*) cat "${PRUNE_MERGED:-/dev/null}" ;;
"pr list --state open"*) cat "${PRUNE_OPEN}" 2>/dev/null || : ;;
esac
GH
cat >"${stubs}/wt" <<'WT'
#!/usr/bin/env bash
echo "wt $*" >>"${PRUNE_LOG}"
WT
chmod +x "${stubs}"/*
export PATH="${stubs}:${PATH}"
logged() { grep -qF -- "$1" "${PRUNE_LOG}"; }

# Clone a: feat/a matches GitHub in a clean worktree; feat/ahead has more.
git -C "${work}/a" fetch -q --prune origin
git -C "${work}/a" worktree add -q "${work}/a-feat" feat/a
git -C "${work}/a" switch -q -c feat/ahead main && commit "${work}/a" ahead.txt x && git -C "${work}/a" push -q origin feat/ahead
commit "${work}/a" ahead.txt y && git -C "${work}/a" switch -q main
# An ignored file only that worktree holds (.env) keeps it, until it is gone.
echo .env >>"${work}/a/.git/info/exclude"
echo SECRET=1 >"${work}/a-feat/.env"
: >"${PRUNE_LOG}"
(cd "${work}/a" && "${prune}" --pushed) >"${work}/prune.out" 2>&1 || fail "prune --pushed must succeed"
logged "force-delete feat/a" && fail "a worktree holding the only copy of an ignored file must be kept"
grep -q 'Kept feat/a: ignored files exist only in .*(.env)' "${work}/prune.out" || fail "a kept worktree must say which ignored files"
rm "${work}/a-feat/.env"
# Many such files: listing only the first few must not kill prune (SIGPIPE).
echo '*.log' >>"${work}/a/.git/info/exclude"
for ((n = 0; n < 50; n++)); do echo "${n}" >"${work}/a-feat/local-${n}.log"; done
(cd "${work}/a" && "${prune}" --pushed) >"${work}/prune-many.out" 2>&1 || fail "prune must survive many local-only ignored files: $(tail -1 "${work}/prune-many.out")"
grep -q 'Kept feat/a: ignored files exist only in' "${work}/prune-many.out" || fail "many local-only ignored files must keep the worktree"
rm "${work}"/a-feat/local-*.log
# Tool state that regenerates itself (.trunk) never keeps a worktree.
echo .trunk >>"${work}/a/.git/info/exclude"
mkdir -p "${work}/a-feat/.trunk/logs" && echo log >"${work}/a-feat/.trunk/logs/cli.log"
: >"${PRUNE_LOG}"
(cd "${work}/a" && "${prune}" --pushed) >/dev/null 2>&1 || fail "prune --pushed must succeed"
logged "wt step prune --foreground" || fail "prune must run wt step prune first"
logged "wt remove --foreground --force-delete feat/a" || fail "a worktree identical to GitHub must be removed"
logged "feat/ahead" && fail "a branch ahead of GitHub must be kept"
logged "remove --foreground --force-delete main" && fail "the default branch must be kept"

# --remote: absorbed branches go, unmerged ones and open PRs stay.
git -C "${work}/seed" fetch -q origin
git -C "${work}/seed" push -q origin origin/main:refs/heads/absorbed origin/main:refs/heads/absorbed-too origin/main:refs/heads/open-pr
echo open-pr >"${PRUNE_OPEN}"
(cd "${work}/a" && "${prune}" --remote --dry-run) >/dev/null 2>&1 || fail "prune --remote --dry-run must succeed"
on_origin absorbed >/dev/null || fail "prune --dry-run must not delete"
# A stash of untracked files only, on main's exact tree, looks "absorbed into
# main" to a tree check; its files live in a parent that check cannot see.
git -C "${work}/seed" switch -q --detach origin/main
echo only-here >"${work}/seed/untracked-only.txt"
git -C "${work}/seed" stash push -q -u
git -C "${work}/seed" push -q origin "$(git -C "${work}/seed" rev-parse 'stash@{0}'):refs/heads/backup/elsewhere/stash-1"
git -C "${work}/seed" stash drop -q
git -C "${work}/a" fetch -q origin
backups_before="$(git -C "${work}/origin.git" for-each-ref refs/heads/backup | wc -l)"
(cd "${work}/a" && DEV_PROFILE_PRUNE_DELETE_BATCH=1 "${prune}" --remote) >/dev/null 2>&1 || fail "prune --remote must succeed"
on_origin absorbed >/dev/null && fail "a branch absorbed into main must be deleted from GitHub"
on_origin absorbed-too >/dev/null && fail "every batch of deletions must run"
[[ "$(git -C "${work}/origin.git" for-each-ref refs/heads/backup | wc -l)" -eq "${backups_before}" ]] ||
	fail "prune --remote must never delete sync's backups"
on_origin open-pr >/dev/null || fail "a branch with an open PR must be kept"
on_origin feat/ahead >/dev/null || fail "an unmerged branch must be kept on GitHub"

# The GitHub-merged sweep: a branch whose tip is exactly a merged PR goes.
: >"${PRUNE_LOG}"
export PRUNE_MERGED="${work}/merged"
echo "feat/ahead $(git -C "${work}/a" rev-parse feat/ahead)" >"${PRUNE_MERGED}"
(cd "${work}/a" && "${prune}") >/dev/null 2>&1 || fail "prune must succeed"
logged "wt remove --foreground --force-delete feat/ahead" || fail "a branch whose tip GitHub merged must be removed"

: >"${PRUNE_LOG}"
echo "feat/ahead 0000000000000000000000000000000000000000" >"${PRUNE_MERGED}"
(cd "${work}/a" && "${prune}") >/dev/null 2>&1 || fail "prune must succeed"
logged "wt remove" && fail "a branch whose tip differs from the merged PR must be kept"
echo "sync fixture ok"
