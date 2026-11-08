#!/usr/bin/env bash
# `wt done` parks unfinished work and restacks each eligible branch onto
# origin/<default>. Real git; wt-sync and gh are stubs that log arguments.
# Usage: done-fixture.sh <generated-dir>
set -euo pipefail

# Absolute: the fixture cds into its own repo before running the scripts.
out="$(cd "${1:?usage: done-fixture.sh <generated-dir>}" && pwd -P)"
done="${out}/bin/dev-profile-done"
[[ -x "$done" ]] || {
	echo "FAIL done fixture: missing ${done}" >&2
	exit 1
}

work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL done fixture: $*" >&2
	exit 1
}

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false
# Setup commits still run prepare-commit-msg (--no-verify does not skip it).
# HK=0 is unset again before invoking done, so a missing script-level export
# still fails the hook-skip case.
export HK=0

stubs="${work}/stubs"
mkdir -p "$stubs"
export WT_LOG="${work}/wt-sync.log"
: >"$WT_LOG"
cat >"${stubs}/wt-sync" <<'STUB'
#!/usr/bin/env bash
echo "wt-sync $*" >>"${WT_LOG}"
if [[ " $* " == *" --all "* ]]; then
	exit 1
fi
exit 0
STUB
cat >"${stubs}/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >>"${WT_LOG}"
if [[ "$1" == pr && "$2" == list ]]; then
	# Real gh --jq '.[0].number' on [] prints nothing.
	[[ "$*" == *--jq* ]] || echo '[]'
	exit 0
fi
exit 1
STUB
chmod +x "${stubs}"/*
export PATH="${stubs}:${PATH}"

commit() { # <repo> <file> <content>
	printf '%s\n' "$3" >"$1/$2"
	git -C "$1" add "$2"
	git -C "$1" commit --no-verify -q -m "$2: $3"
}

origin=""
repo=""
setup_clone() { # <name>
	origin="${work}/${1}.git"
	repo="${work}/${1}"
	git init -q --bare --initial-branch=main "$origin"
	git clone -q "$origin" "$repo" 2>/dev/null
	git -C "$repo" config user.email t@example.com
	git -C "$repo" config user.name t
	git -C "$repo" config commit.gpgsign false
	git -C "$repo" config dev-profile.sync-clone "$1"
	git -C "$repo" switch -q -c main
	commit "$repo" base.txt base
	git -C "$repo" push --no-verify -q origin main
	git -C "$origin" symbolic-ref HEAD refs/heads/main
	git -C "$repo" remote set-head origin main
}

run_done() {
	local dir="$1"
	shift
	: >"$WT_LOG"
	# The script under test must set HK=0; the fixture must not.
	(cd "$dir" && unset HK && "$done" "$@")
}

called_wt_sync_all() {
	grep -q -- '--all' "$WT_LOG"
}

# --- Hook skip: parking must ignore core.hooksPath quality hooks.
setup_clone park
git -C "$repo" switch -q -c feat/park
commit "$repo" tracked.txt original
printf 'dirty\n' >"${repo}/tracked.txt"
hooks="${work}/hooks"
mkdir -p "$hooks"
for hook in pre-commit pre-push; do
	cat >"${hooks}/${hook}" <<'HOOK'
#!/usr/bin/env bash
echo blocked >&2
exit 1
HOOK
	chmod +x "${hooks}/${hook}"
done
git -C "$repo" config core.hooksPath "$hooks"
run_done "$repo" --no-pr --no-prune >"${work}/park.out" 2>&1 || fail "done must park dirty work: $(cat "${work}/park.out")"
[[ "$(git -C "$repo" show feat/park:tracked.txt)" == dirty ]] || fail "the save commit must hold the dirty file"
[[ "$(git -C "$repo" log -1 --format=%s feat/park)" == "chore: save uncommitted work on feat/park" ]] ||
	fail "the save commit must use the parking message"
git -C "$origin" rev-parse --verify --quiet refs/heads/feat/park >/dev/null || fail "origin must have feat/park"
[[ "$(git -C "$origin" show feat/park:tracked.txt)" == dirty ]] || fail "origin must have the parked file"
called_wt_sync_all && fail "wt-sync --all must not be called: $(cat "$WT_LOG")"

# --- Backup is not a restack parent.
setup_clone stack
git -C "$repo" switch -q -c backup/snap main
commit "$repo" snap.txt snap-only
snap_sha="$(git -C "$repo" rev-parse backup/snap)"
git -C "$repo" switch -q -c feat/stacked
commit "$repo" stacked.txt stacked
git -C "$repo" switch -q main
git -C "$repo" worktree add -q "${work}/stack-feat" feat/stacked
commit "$repo" extra.txt extra
git -C "$repo" push --no-verify -q origin main
run_done "$repo" --no-pr --no-prune >"${work}/stack.out" 2>&1 || fail "done must restack onto origin/main: $(cat "${work}/stack.out")"
git -C "$repo" merge-base --is-ancestor origin/main feat/stacked || fail "feat/stacked must be restacked onto origin/main"
[[ "$(git -C "$repo" rev-parse feat/stacked^)" != "$(git -C "$repo" rev-parse backup/snap)" ]] ||
	fail "feat/stacked must not have backup/snap as first parent"
git -C "$repo" show-ref --verify --quiet refs/heads/backup/snap || fail "backup/snap must still exist locally"
[[ "$(git -C "$repo" rev-parse backup/snap)" == "${snap_sha}" ]] || fail "backup/snap must stay at its original tip"
called_wt_sync_all && fail "wt-sync --all must not be called: $(cat "$WT_LOG")"

# --- One conflict does not stop others.
setup_clone split
git -C "$repo" switch -q -c feat/clash main
commit "$repo" clash.txt v1
git -C "$repo" push --no-verify -q origin feat/clash
git -C "$repo" reset --hard -q main
commit "$repo" clash.txt v2
clash_before="$(git -C "$repo" rev-parse feat/clash)"
git -C "$repo" switch -q -c feat/clean main
git -C "$repo" push --no-verify -q origin feat/clean
commit "$repo" clean.txt yes
clean_tip="$(git -C "$repo" rev-parse feat/clean)"
git -C "$repo" switch -q main
run_done "$repo" --no-pr --no-prune >"${work}/split.out" 2>&1 || fail "a single conflict must not fail done: $(cat "${work}/split.out")"
[[ "$(git -C "$origin" rev-parse feat/clean)" == "${clean_tip}" ]] || fail "the clean branch must reach origin"
[[ "$(git -C "$repo" rev-parse feat/clash)" == "${clash_before}" ]] || fail "the diverged local tip must stay unchanged"
[[ "$(git -C "$origin" rev-parse "backup/conflicts/split/feat/clash")" == "${clash_before}" ]] ||
	fail "the diverged tip must be copied to backup/conflicts/<clone>/<branch>"
called_wt_sync_all && fail "wt-sync --all must not be called: $(cat "$WT_LOG")"

# --- No worktree: restack must not switch the primary clone off main.
setup_clone stay
git -C "$repo" switch -q -c feat/loose
commit "$repo" loose.txt loose
loose_tip="$(git -C "$repo" rev-parse feat/loose)"
git -C "$repo" switch -q main
commit "$repo" extra.txt extra
git -C "$repo" push --no-verify -q origin main
run_done "$repo" --no-pr --no-prune >"${work}/stay.out" 2>&1 || fail "done must push a branch with no worktree: $(cat "${work}/stay.out")"
[[ "$(git -C "$repo" symbolic-ref --short HEAD)" == main ]] ||
	fail "done must leave the primary clone on main, not $(git -C "$repo" symbolic-ref --short HEAD 2>/dev/null || git -C "$repo" rev-parse --short HEAD)"
[[ "$(git -C "$origin" rev-parse feat/loose)" == "${loose_tip}" ]] || fail "a branch with no worktree must still be pushed as-is"

# --- Conflict backup matching the branch tip must not fail done.
setup_clone same
git -C "$repo" switch -q -c feat/same
commit "$repo" extra.txt from-feat
git -C "$repo" push --no-verify -q origin feat/same
git -C "$repo" switch -q main
git -C "$repo" worktree add -q "${work}/same-feat" feat/same
commit "$repo" extra.txt from-main
git -C "$repo" push --no-verify -q origin main
run_done "$repo" --no-prune >"${work}/same.out" 2>&1 || fail "a same-commit conflict PR must not fail done: $(cat "${work}/same.out")"
grep -q 'pr create' "$WT_LOG" && fail "open_pr must not create a PR with no commits: $(cat "$WT_LOG")"

# --- --dry-run still only fetches.
setup_clone dry
git -C "$repo" switch -q -c feat/dry
commit "$repo" dry.txt a
printf 'b\n' >"${repo}/dry.txt"
dirty_before="$(git -C "$repo" status --porcelain)"
run_done "$repo" --dry-run --no-pr --no-prune >"${work}/dry.out" 2>&1 || fail "done --dry-run must succeed: $(cat "${work}/dry.out")"
[[ "$(git -C "$repo" status --porcelain)" == "${dirty_before}" ]] || fail "dry-run must leave the dirty file uncommitted"
grep -Eq 'would-restack +origin/main' "${work}/dry.out" || fail "dry-run must restack onto origin/main: $(cat "${work}/dry.out")"
grep -F 'wt-sync --all' "${work}/dry.out" && fail "dry-run must not restack with wt-sync --all: $(cat "${work}/dry.out")"
grep -Fq 'dry-run: fetched origin; no other changes' "${work}/dry.out" || fail "dry-run must only fetch"

# --- Parallel execution across worktrees and branches (with and without --drop).
real_git="$(command -v git)"
export REAL_GIT="$real_git"
export PAR_DIR="${work}/par-track"
mkdir -p "$PAR_DIR"

cat >"${stubs}/git" <<'STUB'
#!/usr/bin/env bash
if [[ "${WT_DONE_TRACK_PARALLEL:-0}" == 1 ]]; then
	phase=""
	for arg in "$@"; do
		case "$arg" in
		commit) phase="commit"; break ;;
		rebase) phase="rebase"; break ;;
		push)
			if [[ " $* " == *" --delete "* ]]; then
				phase="prune-remote"
			else
				phase="push"
			fi
			break
			;;
		remove)
			if [[ " $* " == *" worktree remove "* ]]; then
				phase="worktree-remove"
				break
			fi
			;;
		--contains)
			phase="drop-contains"
			break
			;;
		--others)
			phase="drop-scan"
			break
			;;
		esac
	done
	if [[ -n "$phase" && " $* " != *" --abort"* ]]; then
		dir="${PAR_DIR}/${phase}"
		mkdir -p "${dir}/active"
		: >"${dir}/active/$$"
		for _ in 1 2 3 4 5 6 7 8; do
			active=( "${dir}/active"/* )
			count="${#active[@]}"
			prev="$(cat "${dir}/peak" 2>/dev/null || echo 0)"
			if ((count > prev)); then
				printf '%s\n' "$count" >"${dir}/peak"
			fi
			((count >= 2)) && break
			sleep 0.03
		done
		rm -f "${dir}/active/$$"
	fi
fi
exec "$REAL_GIT" "$@"
STUB

cat >"${stubs}/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >>"${WT_LOG}"
if [[ "${WT_DONE_TRACK_PARALLEL:-0}" == 1 && "$1" == pr && "$2" == create ]]; then
	dir="${PAR_DIR}/pr"
	mkdir -p "${dir}/active"
	: >"${dir}/active/$$"
	for _ in 1 2 3 4 5 6 7 8; do
		active=( "${dir}/active"/* )
		count="${#active[@]}"
		prev="$(cat "${dir}/peak" 2>/dev/null || echo 0)"
		if ((count > prev)); then
			printf '%s\n' "$count" >"${dir}/peak"
		fi
		((count >= 2)) && break
		sleep 0.03
	done
	rm -f "${dir}/active/$$"
	echo "https://example.invalid/pr/1"
	exit 0
fi
if [[ "$1" == pr && "$2" == list ]]; then
	[[ "$*" == *--jq* ]] || echo '[]'
	exit 0
fi
exit 1
STUB

cat >"${stubs}/trash" <<'STUB'
#!/usr/bin/env bash
echo "trash $*" >>"${WT_LOG}"
rm -rf "$@"
STUB
chmod +x "${stubs}/git" "${stubs}/gh" "${stubs}/trash"

peak_of() {
	cat "${PAR_DIR}/${1}/peak" 2>/dev/null || echo 0
}

setup_clone par
for b in merged-1 merged-2; do
	git -C "$repo" switch -q -c "$b" main
	git -C "$repo" push --no-verify -q origin "$b"
done
git -C "$repo" switch -q main
git -C "$repo" branch -D -q merged-1 merged-2
for b in p1 p2 p3; do
	git -C "$repo" switch -q -c "feat/${b}" main
	commit "$repo" "${b}.txt" "base-${b}"
	git -C "$repo" switch -q main
	git -C "$repo" worktree add -q "${work}/par-${b}" "feat/${b}"
	printf 'dirty-%s\n' "$b" >"${work}/par-${b}/${b}.txt"
done
commit "$repo" main-advance.txt advanced
git -C "$repo" push --no-verify -q origin main

WT_DONE_TRACK_PARALLEL=1 DEV_PROFILE_DONE_JOBS=4 run_done "$repo" >"${work}/par.out" 2>&1 ||
	fail "parallel done without --drop must succeed: $(cat "${work}/par.out")"
for b in p1 p2 p3; do
	[[ "$(git -C "$origin" show "feat/${b}:${b}.txt")" == "dirty-${b}" ]] ||
		fail "origin/feat/${b} must hold dirty-${b}"
	git -C "$origin" cat-file -e "feat/${b}:main-advance.txt" ||
		fail "origin/feat/${b} must be restacked onto origin/main"
	[[ ! -d "${work}/par-${b}" ]] || fail "worktree par-${b} must be pruned"
done
for b in merged-1 merged-2; do
	git -C "$origin" rev-parse --verify --quiet "refs/heads/${b}" >/dev/null &&
		fail "origin/${b} must be pruned"
done
for phase in commit rebase push pr worktree-remove prune-remote; do
	(("$(peak_of "$phase")" >= 2)) ||
		fail "phase '${phase}' must run in parallel (saw peak=$(peak_of "$phase")): $(cat "${work}/par.out")"
done

# Deterministic --drop in parallel: danger scan and branch containment run in parallel, then trash drops the clone.
rm -rf "${PAR_DIR:?}"/*
setup_clone pardrop
for b in backup/b1 backup/b2; do
	git -C "$repo" switch -q -c "$b" main
	commit "$repo" "${b//\//-}.txt" "$b"
	git -C "$repo" push --no-verify -q origin "$b"
done
git -C "$repo" switch -q main
for b in d1 d2 d3; do
	git -C "$repo" switch -q -c "feat/${b}" main
	commit "$repo" "${b}.txt" "val-${b}"
	git -C "$repo" switch -q main
	git -C "$repo" worktree add -q "${work}/pardrop-${b}" "feat/${b}"
	printf 'untracked-%s\n' "$b" >"${work}/pardrop-${b}/untracked-${b}.txt"
done
WT_DONE_TRACK_PARALLEL=1 DEV_PROFILE_DONE_JOBS=4 run_done "$repo" --drop >"${work}/pardrop.out" 2>&1 ||
	fail "parallel done --drop must succeed: $(cat "${work}/pardrop.out")"
[[ ! -d "$repo" ]] || fail "done --drop must trash the primary clone"
grep -q "trash ${repo}" "$WT_LOG" || fail "done --drop must invoke trash on ${repo}"
for phase in commit push drop-contains drop-scan; do
	(("$(peak_of "$phase")" >= 2)) ||
		fail "drop phase '${phase}' must run in parallel (saw peak=$(peak_of "$phase")): $(cat "${work}/pardrop.out")"
done

# --- Gutted worktree (tracked files missing on disk, ignored oversized cache left behind) and positional repo arg.
setup_clone gutted
git -C "$repo" switch -q -c feat/merged main
commit "$repo" merged.txt merged
git -C "$repo" switch -q main
git -C "$repo" merge --ff-only -q feat/merged
commit "$repo" .gitignore ".next/"
git -C "$repo" push -q origin main
# The worktree's checkout is gutted, so no tracked ignore file survives there.
# Pin .next/ in the repository's own exclude so the leftover cache is ignored
# without leaning on the runner's global excludes file.
printf '.next/\n' >>"${repo}/.git/info/exclude"
git -C "$repo" worktree add -q "${work}/gutted-wt" feat/merged
rm -f "${work}/gutted-wt/base.txt" "${work}/gutted-wt/merged.txt"
mkdir -p "${work}/gutted-wt/apps/web/.next/cache"
head -c 2097152 /dev/zero >"${work}/gutted-wt/apps/web/.next/cache/0.pack"
cd_directive="${work}/cd-directive"
WORKTRUNK_DIRECTIVE_CD_FILE="${cd_directive}" DEV_PROFILE_SYNC_MAX_FILE_MB=1 run_done "$repo" --drop gutted >"${work}/gutted.out" 2>&1 ||
	fail "done --drop on gutted worktree must succeed: $(cat "${work}/gutted.out")"
test ! -d "$repo" && test ! -d "${work}/gutted-wt" || fail "done --drop must remove gutted worktree and trash primary clone"
git -C "$origin" rev-parse --verify --quiet refs/heads/feat/merged >/dev/null &&
	fail "already-merged gutted worktree branch must not be pushed as a deletion commit to origin"
test "$(cat "${cd_directive}")" = "${work}" || fail "done --drop must write parent dir to WORKTRUNK_DIRECTIVE_CD_FILE"

# --- Stash conflicting with advanced main and existing origin/wip must still park onto wip-2 and drop.
setup_clone stashclash
git -C "$repo" switch -q -c wip main
commit "$repo" parked.txt parked
git -C "$repo" push -q origin wip
git -C "$repo" switch -q main
git -C "$repo" branch -D -q wip
printf 'stashed-version\n' >"${repo}/base.txt"
mkdir -p "${repo}/storage/logos"
printf 'logo-bytes\n' >"${repo}/storage/logos/a.txt"
git -C "$repo" add storage/logos/a.txt
git -C "$repo" stash push -q -m "old stash on main"
commit "$repo" base.txt main-advanced-version
git -C "$repo" push -q origin main
run_done "$repo" --drop >"${work}/stashclash.out" 2>&1 ||
	fail "done --drop with conflicting stash and origin/wip must succeed: $(cat "${work}/stashclash.out")"
test ! -d "$repo" || fail "done --drop must trash stashclash clone"
test "$(git -C "$origin" show wip:parked.txt)" = parked || fail "existing origin/wip must not be overwritten"
test "$(git -C "$origin" show wip-2:base.txt)" = stashed-version || fail "stash must be parked onto origin/wip-2"
test "$(git -C "$origin" show wip-2:storage/logos/a.txt)" = logo-bytes || fail "stash tracked additions must be on origin/wip-2"
# The script itself must disable quality hooks; the fixture did not export HK=0.
grep -Fq 'export HK=0' "$done" || fail "dev-profile-done must export HK=0 so hk cannot block parking"
grep -Eq 'commit -q --no-verify' "$done" || fail "dev-profile-done commits must pass --no-verify"
grep -Eq 'push --quiet --no-verify' "$done" || fail "dev-profile-done pushes must pass --no-verify"

# --- A declared submodule with no checkout holds no local work; drop must proceed.
setup_clone submodule
git -C "$repo" config -f .gitmodules submodule.corpus.path corpus
git -C "$repo" config -f .gitmodules submodule.corpus.url "${work}/missing-corpus.git"
git -C "$repo" add .gitmodules
git -C "$repo" update-index --add --cacheinfo "160000,839da3d154de36feda5fb736d7ad14f80a505302,corpus"
git -C "$repo" commit --no-verify -q -m "submodule: add corpus gitlink"
git -C "$repo" push --no-verify -q origin main
run_done "$repo" --drop >"${work}/submodule.out" 2>&1 ||
	fail "done --drop must ignore a declared submodule with no checkout: $(cat "${work}/submodule.out")"
test ! -d "$repo" || fail "done --drop must trash a clone whose declared submodule has no checkout"

# --- A populated submodule with unpushed work still stops the drop.
setup_clone submodule-work
git init -q --bare --initial-branch=main "${work}/corpus.git"
git clone -q "${work}/corpus.git" "${work}/corpus-src"
git -C "${work}/corpus-src" config user.email t@example.com
git -C "${work}/corpus-src" config user.name t
printf 'corpus\n' >"${work}/corpus-src/data.txt"
git -C "${work}/corpus-src" add data.txt
git -C "${work}/corpus-src" commit --no-verify -q -m "corpus: data"
git -C "${work}/corpus-src" push --no-verify -q origin main
git -C "$repo" config -f .gitmodules submodule.corpus.path corpus
git -C "$repo" config -f .gitmodules submodule.corpus.url "${work}/corpus.git"
git -C "$repo" add .gitmodules
git -C "$repo" update-index --add --cacheinfo "160000,$(git -C "${work}/corpus-src" rev-parse HEAD),corpus"
git -C "$repo" commit --no-verify -q -m "submodule: add corpus gitlink"
git -C "$repo" push --no-verify -q origin main
git -c protocol.file.allow=always -C "$repo" submodule update --init -q -- corpus
printf 'local\n' >"${repo}/corpus/local.txt"
git -C "${repo}/corpus" add local.txt
git -C "${repo}/corpus" commit --no-verify -q -m "corpus: local only"
run_done "$repo" --drop >"${work}/submodule-work.out" 2>&1 &&
	fail "done --drop must refuse a populated submodule with unpushed work"
grep -q "nested repository" "${work}/submodule-work.out" || fail "the refusal must name the nested repository"
test -d "$repo" || fail "done --drop must keep a clone holding submodule work"
echo "done fixture ok"
