#!/usr/bin/env bash
set -euo pipefail
# Edit lib/prune.sh: `mise run generate` copies it into bin/.

# Remove what is already safe on GitHub. Always: worktrees and branches
# merged into the default branch (wt step prune), and branches whose tip is
# exactly a PR GitHub merged (squash merges wt cannot prove integrated).
#   --pushed  also clean worktrees and branches whose tip equals GitHub's
#   --remote  also branches on GitHub already absorbed into the default branch
#             (never one with an open PR)
# Other flags go to wt step prune; --dry-run previews everything.
dry_run=false pushed=false remote=false
args=()
for arg in "$@"; do
	case "${arg}" in
	--pushed)
		pushed=true
		continue
		;;
	--remote)
		remote=true
		continue
		;;
	--foreground) continue ;; # always foreground, so the sweeps below see the result
	--dry-run) dry_run=true ;;
	esac
	args+=("${arg}")
done

# shellcheck source=lib/sh/repo-facts.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/repo-facts.sh"
wt step prune --foreground ${args[@]+"${args[@]}"}

# shellcheck source=lib/sh/github.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/github.sh"
# shellcheck source=lib/sh/remove-merged.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/remove-merged.sh"

# remove <branch> <reason> [wt remove flags...]: honours --dry-run.
remove() {
	local branch="$1" reason="$2"
	shift 2
	if [[ "${dry_run}" == true ]]; then
		echo "Would remove ${branch}: ${reason}"
	else
		wt remove --foreground "$@" "${branch}" || echo "Kept ${branch}" >&2
	fi
}

merged="$(ghr pr list --state merged --limit "${DEV_PROFILE_PRUNE_PR_LIMIT:-200}" \
	--json headRefName,headRefOid,headRepositoryOwner \
	--jq ".[] | select(.headRepositoryOwner.login == \"${owner}\") | \"\(.headRefName) \(.headRefOid)\"")"

# fd 3 keeps wt's stdin free for approval prompts.
while read -r name oid <&3; do
	[[ -n "${name}" && "${name}" != "${default_branch}" ]] || continue
	[[ "$(git rev-parse --verify --quiet "refs/heads/${name}")" == "${oid}" ]] || continue
	if [[ "${dry_run}" == true ]]; then
		echo "Would remove ${name}: its PR merged on GitHub"
	else
		remove_merged "${name}" "${oid}" || echo "Kept ${name}" >&2
	fi
done 3<<<"${merged}"

if [[ "${pushed}" == true ]]; then
	primary="$(worktrees | sed -n 1p | cut -d "${sep}" -f1)"

	# Ignored paths tools regenerate on their own (space-separated), which never
	# make a worktree worth keeping.
	disposable="${DEV_PROFILE_PRUNE_DISPOSABLE-.trunk}"

	# Ignored files in worktree $1 (.env, local config) that the primary worktree
	# lacks or holds differently: removing the worktree would destroy them.
	unique_ignored() {
		local path tool_state
		while IFS= read -r -d '' path; do
			[[ "${path}" == '!! '* ]] || continue
			path="${path#!! }"
			path="${path%/}"
			for tool_state in ${disposable}; do
				[[ "${path}" != "${tool_state}" && "${path}" != "${tool_state}/"* ]] || continue 2
			done
			if [[ -d "$1/${path}" ]]; then
				[[ -e "${primary}/${path}" ]] || echo "${path}"
			else
				cmp -s "$1/${path}" "${primary}/${path}" || echo "${path}"
			fi
		done < <(git -C "$1" status --porcelain=v1 -z --ignored)
	}

	while read -r branch tip <&3; do
		[[ "${branch}" != "${default_branch}" ]] || continue
		[[ "$(git rev-parse --verify --quiet "refs/remotes/origin/${branch}")" == "${tip}" ]] || continue
		dir="" locked=""
		IFS="${sep}" read -r dir _ _ locked < <(worktree_of "${branch}") || true
		[[ "${dir}" != "${primary}" && -z "${locked}" ]] || continue
		if [[ -n "${dir}" ]]; then
			[[ -z "$(git -C "${dir}" status --porcelain)" ]] || continue
			only_here="$(unique_ignored "${dir}" | awk 'NR <= 3' | paste -sd, -)"
			if [[ -n "${only_here}" ]]; then
				echo "Kept ${branch}: ignored files exist only in ${dir} (${only_here}); remove it yourself once they are safe" >&2
				continue
			fi
		fi
		remove "${branch}" "identical to GitHub's copy" --force-delete
	done 3< <(git for-each-ref --format='%(refname:short) %(objectname)' refs/heads)
fi

if [[ "${remote}" == true ]]; then
	doomed=() leases=()
	open="$(ghr pr list --state open --limit 1000 --json headRefName,headRepositoryOwner \
		--jq ".[] | select(.headRepositoryOwner.login == \"${owner}\") | .headRefName")"
	while read -r branch tip <&3; do
		[[ "${branch}" != "${default_branch}" && "${branch}" != HEAD ]] || continue
		# Never sync's backups: a stash keeps untracked files in a parent that
		# "absorbed into main" cannot see. Delete those by hand once restored.
		[[ "${branch}" != backup/* ]] || continue
		grep -qxF -- "${branch}" <<<"${open}" && continue
		adds_nothing "${tip}" "${base}" || continue # squash merges count too
		if [[ "${dry_run}" == true ]]; then
			echo "Would delete origin/${branch}: absorbed into ${default_branch}"
		else
			doomed+=("${branch}")
			leases+=("--force-with-lease=refs/heads/${branch}:${tip}")
		fi
	done 3< <(git for-each-ref --format='%(refname:lstrip=3) %(objectname)' refs/remotes/origin)

	# Delete in batches: pre-push hooks run once per push, not once per branch.
	# Each lease names the tip judged absorbed, so a branch moved since is kept.
	batch="${DEV_PROFILE_PRUNE_DELETE_BATCH:-100}"
	for ((i = 0; i < ${#doomed[@]}; i += batch)); do
		git push --quiet "${leases[@]:i:batch}" --delete origin "${doomed[@]:i:batch}" ||
			echo "A batch of deletions was refused; see above" >&2
	done
	if [[ "${#doomed[@]}" -gt 0 ]]; then
		git fetch --prune --quiet origin
		for branch in "${doomed[@]}"; do
			if git rev-parse --verify --quiet "refs/remotes/origin/${branch}" >/dev/null; then
				echo "Kept origin/${branch}: GitHub refused the deletion" >&2
			else
				echo "Deleted origin/${branch}: absorbed into ${default_branch}"
			fi
		done
	fi
fi
