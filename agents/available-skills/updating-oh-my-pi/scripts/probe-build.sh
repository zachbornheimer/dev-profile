#!/usr/bin/env bash
# Global hook.* git config (hk) fires even with core.hooksPath unset; CI has no hooks. HK=0 is their documented off switch.
export HK=0
# probe-build.sh: run the omp-build checks locally exactly as CI runs them.
#
# Works in an ephemeral blobless clone under $TMPDIR (never touches a checkout:
# --repo only lends its objects and remote URLs). Mirrors, step for step:
#   .github/workflows/omp-build.yml  "Merge topic branches into omp-build"
#     rerere cache seeding from .omp-build/rr-cache, `git merge --no-ff
#     --rerere-autoupdate`, `bun .omp-build/resolve-conflicts.ts <branch>`,
#     the merge-only guard on `assembled`, `.omp-build/merge-fix/<branch>.patch`
#     (git apply --index + commit --amend). The scripts it runs are the ones in
#     the base commit's .omp-build/, not copies.
#   .github/workflows/protect-main.yml  (with --pr-head) the zysys
#     protect_main_paths.py guard, with allowed_paths read from that workflow.
#   omp-build.yml build job  (--build) `bun install --frozen-lockfile` and a
#     bundle of packages/coding-agent/src/cli.ts. It catches bundler errors
#     (missing export, undeclared private name); the Rust addon still needs CI.
#
# The base is fork/main (what CI assembles onto), or --pr-head REV (a PR head:
# its own .omp-build/ is used, as protect-main's verify-assembly does).
#
# Usage: probe-build.sh [--base REF] [--pr-head REV [--pr-base REV]] [--add BRANCH]...
#                       [--drop BRANCH]... [--pin BRANCH=SHA]... [--build|--no-build] [--repo PATH]
#   --base REF     assemble onto REF instead of fork/main
#   --pr-head REV  probe a PR head: assemble onto it, run the protect-main guard
#   --pr-base REV  the PR base for the guard (default fork/main)
#   --add BRANCH   append BRANCH (must already be pushed to the fork)
#   --drop BRANCH  leave BRANCH out of this probe
#   --pin B=SHA    merge SHA instead of the fork tip of B (a push not yet on the fork)
#   --build        also bundle the coding agent (default on with --pr-head)
#   --no-build     skip the bundle check
#   --tree REV     only bundle-check an already assembled tree (e.g. the omp-build tip CI built)
#   --repo PATH    optional checkout whose objects and remote URLs are reused
#                  (default $OMP_REPO if it exists)
# Exit: 0 every check passes; 1 CI would reject (the CI error text is printed);
# 2 usage or fetch error.
set -euo pipefail

repo="${OMP_REPO:-}"
adds=()
drops=()
bases=()
pins=""
pr_head=""
pr_base=""
build=auto
tree=""
while [ $# -gt 0 ]; do
	case "$1" in
	--build)
		build=1
		shift
		;;
	--no-build)
		build=0
		shift
		;;
	--add | --drop | --repo | --base | --pin | --pr-head | --pr-base | --tree)
		[ $# -ge 2 ] || {
			echo "$1 needs a value" >&2
			exit 2
		}
		case "$1" in
		--add) adds+=("$2") ;;
		--drop) drops+=("$2") ;;
		--repo) repo="$2" ;;
		--base) bases+=("$2") ;;
		--pin) pins="$pins$2"$'\n' ;;
		--pr-head) pr_head="$2" ;;
		--pr-base) pr_base="$2" ;;
		--tree) tree="$2" ;;
		esac
		shift 2
		;;
	-h | --help)
		sed -n '2,36p' "$0"
		exit 0
		;;
	*)
		echo "unknown argument: $1" >&2
		exit 2
		;;
	esac
done
[ "$build" = auto ] && { [ -n "$pr_head" ] && build=1 || build=0; }

command -v bun >/dev/null 2>&1 || {
	echo "bun is required to run .omp-build/resolve-branches.ts" >&2
	exit 2
}
staged="$(mktemp -d "${TMPDIR:-/tmp}/probe-omp-build.XXXXXX")"
trap 'rm -rf "$staged"' EXIT
t0=$SECONDS
stamp() { echo "  [$((SECONDS - t0))s] $*" >&2; }

# Remote names are not fixed across checkouts: this skill's layout calls the
# fork `fork` and upstream `origin`, while a plain clone of the fork calls them
# `origin` and `upstream`. Resolve both by URL; the ephemeral clone always uses
# `fork` and `origin`.
fork_url=https://github.com/zachbornheimer/oh-my-pi.git
base_url=https://github.com/can1357/oh-my-pi.git
alternates=""
if [ -n "$repo" ] && git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
	f=""
	o=""
	for name in $(git -C "$repo" remote); do
		url="$(git -C "$repo" remote get-url "$name" 2>/dev/null || true)"
		case "$url" in
		*zachbornheimer/oh-my-pi*) f="$url" ;;
		*can1357/oh-my-pi*) o="$url" ;;
		esac
	done
	[ -n "$f" ] || f="$(git -C "$repo" remote get-url fork 2>/dev/null || true)"
	[ -n "$o" ] || o="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
	[ -n "$f" ] && fork_url="$f"
	[ -n "$o" ] && base_url="$o"
	alternates="$(cd "$repo" && cd "$(git rev-parse --git-path objects)" && pwd)"
fi

work="$staged/repo"
git init -q "$work"
cd "$work"
git remote add fork "$fork_url"
git remote add origin "$base_url"
[ -z "$alternates" ] || echo "$alternates" >.git/objects/info/alternates
# The merge commits are throwaway: carry the probe's own identity, like CI's bot.
git config user.name "omp-build probe"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git config commit.gpgsign false
git config core.hooksPath /dev/null
git config rerere.enabled true
git config rerere.autoupdate true
git config advice.detachedHead false

git fetch -q --filter=blob:none origin main || exit 2
git fetch -q --filter=blob:none fork main || exit 2
stamp "fetched origin/main and fork/main"

bundle_check() {
	bun install --frozen-lockfile >"$staged/install.log" 2>&1 || {
		echo "  FAIL     bun install --frozen-lockfile"
		tail -8 "$staged/install.log" | sed 's/^/    /'
		exit 1
	}
	stamp "bun install"
	# The compile step needs the Rust addon (CI-only); the bundler alone reports
	# missing exports and undeclared private names.
	# omp-legacy-pi-modules is a virtual module that CI's scripts/legacy-pi-virtual-module.ts plugin supplies; keep it external.
	if ! bun build packages/coding-agent/src/cli.ts --target=bun --external omp-legacy-pi-modules --outdir "$staged/out" >"$staged/build.log" 2>&1; then
		echo "  FAIL     bundle packages/coding-agent/src/cli.ts"
		grep -E 'error:|^[0-9]+ \|' "$staged/build.log" | head -12 | sed 's/^/    /'
		exit 1
	fi
	stamp "bundle"
}

if [ -n "$tree" ]; then
	git rev-parse --verify -q "$tree^{commit}" >/dev/null || git fetch -q --filter=blob:none fork "$tree" || exit 2
	git checkout -q --detach "$tree"
	bundle_check
	echo "bundle clean: $tree"
	exit 0
fi

if [ -n "$pr_head" ]; then
	git rev-parse --verify -q "$pr_head^{commit}" >/dev/null 2>&1 || git fetch -q --filter=blob:none fork "$pr_head" 2>/dev/null || true
	upstream="$(git rev-parse --verify -q "$pr_head^{commit}" 2>/dev/null || git rev-parse --verify -q FETCH_HEAD)" || {
		echo "--pr-head $pr_head does not resolve to a commit" >&2
		exit 2
	}
elif [ "${#bases[@]}" -gt 0 ]; then
	upstream="${bases[${#bases[@]}-1]}"
	git rev-parse --verify -q "$upstream^{commit}" >/dev/null || git fetch -q --filter=blob:none fork "$upstream" 2>/dev/null || true
	upstream="$(git rev-parse --verify -q "$upstream^{commit}")" || {
		echo "--base ${bases[${#bases[@]}-1]} does not resolve to a commit" >&2
		exit 2
	}
else
	# The base CI assembles onto: fork main, upstream plus the carry commit.
	upstream="$(git rev-parse refs/remotes/fork/main)"
	git merge-base "$upstream" refs/remotes/origin/main >/dev/null || {
		echo "fork/main and origin/main have no merge-base" >&2
		exit 1
	}
	behind="$(git rev-list --count "$upstream..refs/remotes/origin/main")"
	[ "$behind" = 0 ] || echo "note: fork/main is $behind commits behind upstream main (merge origin/main into it; do not push main by hand)" >&2
fi

# protect-main (PR heads only): the same guard script CI runs, on the PR range.
if [ -n "$pr_head" ]; then
	prb="${pr_base:-$(git rev-parse refs/remotes/fork/main)}"
	git rev-parse --verify -q "$prb^{commit}" >/dev/null || git fetch -q --filter=blob:none fork "$prb" 2>/dev/null || true
	prb="$(git rev-parse --verify -q "$prb^{commit}")" || {
		echo "--pr-base does not resolve to a commit" >&2
		exit 2
	}
	guard="${PROBE_GUARD_SCRIPT:-}"
	if [ -z "$guard" ]; then
		guard="$staged/protect_main_paths.py"
		gh api repos/zysys/github-workflows/contents/scripts/protect_main_paths.py --jq .content 2>/dev/null | base64 -d >"$guard" ||
			curl -fsSL https://raw.githubusercontent.com/zysys/github-workflows/main/scripts/protect_main_paths.py -o "$guard" || {
			echo "cannot fetch zysys/github-workflows protect_main_paths.py (set PROBE_GUARD_SCRIPT)" >&2
			exit 2
		}
	fi
	wf="$(git show "$upstream:.github/workflows/protect-main.yml")" || {
		echo "cannot read .github/workflows/protect-main.yml at the PR head" >&2
		exit 2
	}
	allowed="$(printf '%s\n' "$wf" | awk '/allowed_paths: \|/{f=1;next} f&&/^[[:space:]]+[^[:space:]]/{if(match($0,/^ +[a-z_]+:/))exit;sub(/^ +/,"");print;next} f{exit}')"
	[ -n "$allowed" ] || {
		echo "no allowed_paths in the PR head's protect-main.yml" >&2
		exit 2
	}
	up_repo="$(printf '%s\n' "$wf" | sed -n 's/^ *upstream_repo: *//p' | head -1)"
	git checkout -q --detach "$upstream"
	rc=0
	guard_out="$(REPO_PATH="$work" ALLOWED_PATHS="$allowed" BASE_SHA="$prb" HEAD_SHA="$upstream" BASE_REF=main HEAD_REF=pr \
		UPSTREAM_REPO="${up_repo:-can1357/oh-my-pi}" UPSTREAM_BRANCH=main UPSTREAM_SHA="$(git rev-parse refs/remotes/origin/main)" \
		POST_COMMENT=false GITHUB_TOKEN= python3 "$guard" 2>&1)" || rc=$?
	if [ "$rc" != 0 ]; then
		echo "  FAIL protect-main: the PR touches files outside the allowed paths ($(printf '%s' "$allowed" | tr '\n' ' '))"
		printf '%s\n' "$guard_out" | grep -E '^\|' | sed 's/^/    /' | head -20
		echo "  fix: keep the PR to .omp-build/** and the two workflows; put code on a topic branch and add .omp-build/branches/<topic>.toml"
		exit 1
	fi
	echo "  clean    protect-main paths"
	stamp "protect-main guard"
else
	git checkout -q --detach "$upstream"
fi
stamp "checked out base"

configured="$(bun .omp-build/resolve-branches.ts "" schedule)" || {
	echo ".omp-build/branches failed to resolve via .omp-build/resolve-branches.ts:" >&2
	bun .omp-build/resolve-branches.ts "" schedule >&2 || true
	exit 2
}

branches=()
while IFS= read -r b; do
	[ -n "$b" ] || continue
	keep=1
	for d in ${drops[@]+"${drops[@]}"}; do
		[ "$b" = "$d" ] && keep=0
	done
	[ "$keep" = 1 ] && branches+=("$b")
done <<<"$configured"
for a in ${adds[@]+"${adds[@]}"}; do
	present=0
	for b in ${branches[@]+"${branches[@]}"}; do
		[ "$b" = "$a" ] && present=1
	done
	[ "$present" = 1 ] || branches+=("$a")
done

if [ ${#branches[@]} -eq 0 ]; then
	echo "no branches: CI refuses this (Branchless assembly)" >&2
	exit 1
fi

# CI seeds the rerere cache before merging.
if [ -d .omp-build/rr-cache ]; then
	mkdir -p "$(git rev-parse --git-path rr-cache)"
	cp -R .omp-build/rr-cache/. "$(git rev-parse --git-path rr-cache)/"
fi

echo "upstream base ${upstream:0:10}"
for b in "${branches[@]}"; do
	ref="refs/remotes/fork/$b"
	pin="$(printf '%s' "$pins" | sed -n "s|^$b=||p" | head -1)"
	if [ -n "$pin" ]; then
		git cat-file -e "$pin^{commit}" 2>/dev/null || git fetch -q --filter=blob:none fork "$pin" 2>/dev/null || true
		git update-ref "$ref" "$pin" 2>/dev/null || {
			echo "  MISSING  $b: pinned $pin is not available locally or on the fork"
			exit 1
		}
	elif ! git fetch -q --filter=blob:none fork "+refs/heads/$b:$ref" 2>/dev/null; then
		echo "  MISSING  $b is not on the fork remote (push it first)"
		exit 1
	fi
	if [ "$b" = "assembled" ]; then
		if git cat-file -e '1dbcad97811e2a1cd00a79a80bf35abacf2db8b5^{commit}' 2>/dev/null; then
			assembled_floor="1dbcad97811e2a1cd00a79a80bf35abacf2db8b5"
		else
			assembled_floor="$(git merge-base HEAD "$ref")"
		fi
		# The guard expression changed across CI revisions: run the one in the base's own workflow.
		guard_expr="$(git show "$upstream:.github/workflows/omp-build.yml" 2>/dev/null | sed -n 's/^ *non_merge="\(.*\)"$/\1/p' | head -1)"
		if [ -n "$guard_expr" ]; then
			branch="$b"
			non_merge="$(eval "printf '%s\n' \"$guard_expr\"" 2>/dev/null || true)"
			unset branch
		else
			non_merge="$(git rev-list --first-parent --no-merges "${assembled_floor}..$ref" --not HEAD 2>/dev/null | head -5 || true)"
		fi
		if [ -n "$non_merge" ]; then
			echo "  FAIL     assembled is a merge-only integration base; move non-merge commits ($(printf '%s' "$non_merge" | tr '\n' ' ')) to a topic branch under .omp-build/branches/<topic>.toml"
			exit 1
		fi
	fi
	if ! git merge --no-ff --no-edit --rerere-autoupdate "$ref" >"$staged/merge.log" 2>&1; then
		if ! bun .omp-build/resolve-conflicts.ts "$b" >"$staged/resolve.log" 2>&1; then
			echo "  CONFLICT $b conflicts with upstream - merge main into the branch, resolve the conflicts and push; do not delete its manifest file to silence this"
			sed 's/^/    /' "$staged/resolve.log" | head -5
			git diff --name-only --diff-filter=U | sed 's/^/    /'
			exit 1
		fi
		conflicts="$(git diff --name-only --diff-filter=U)"
		if [ -z "$conflicts" ] && [ -f "$(git rev-parse --git-path MERGE_HEAD)" ]; then
			git commit -q --no-edit
		elif [ -z "$conflicts" ]; then
			echo "  FAIL     git merge $b failed without unmerged paths"
			sed 's/^/    /' "$staged/merge.log" | tail -5
			exit 1
		else
			echo "  CONFLICT $b conflicts with upstream - merge main into the branch, resolve the conflicts and push; do not delete its manifest file to silence this"
			printf '%s\n' "$conflicts" | sed 's/^/    /'
			exit 1
		fi
	fi
	if [ -f ".omp-build/merge-fix/$b.patch" ]; then
		if ! git apply --index ".omp-build/merge-fix/$b.patch" 2>"$staged/fix.log"; then
			echo "  FAIL     .omp-build/merge-fix/$b.patch does not apply after merging $b"
			sed 's/^/    /' "$staged/fix.log" | head -5
			exit 1
		fi
		git commit -q --amend --no-edit
		echo "  clean    $b (merge-fix applied)"
	else
		echo "  clean    $b"
	fi
done
stamp "merged ${#branches[@]} branches"

[ "$build" = 1 ] && bundle_check
echo "assembly clean: ${#branches[@]} branches merge in order"
