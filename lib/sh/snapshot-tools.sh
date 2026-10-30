# shellcheck shell=bash
# Sourced by the profile's bin/ scripts: Snapshot helpers the sync and retire scripts share.
# Edit lib/sh/snapshot-tools.sh: `mise run generate` copies it into lib/.

clone_id() { git config --get dev-profile.sync-clone || :; }

report() { printf '  %-13s %s\n' "$1" "$2"; }

# A commit of HEAD plus every staged, unstaged and untracked change in
# worktree $1, built in a scratch index: the worktree itself is untouched.
# A file over the size limit keeps its committed version (or stays out, if
# new) and is recorded in ${left_out}. A nested repository is recorded as a
# pointer only, listed in ${nested} and reported: run wt sync inside it.
snapshot() {
	local index tree path size
	index="$(mktemp)"
	cp "$(git -C "$1" rev-parse --path-format=absolute --git-path index)" "${index}"
	GIT_INDEX_FILE="${index}" git -C "$1" add -A 2>/dev/null # quiet about nested repositories; a failure still stops here
	while IFS= read -r -d '' path; do
		size="$(GIT_INDEX_FILE="${index}" git -C "$1" cat-file -s ":${path}" 2>/dev/null)" || continue
		if ((size > ${max_file_mb:?} * 1024 * 1024)); then
			GIT_INDEX_FILE="${index}" git -C "$1" reset --quiet HEAD -- "${path}"
			echo "$1/${path}" >>"${left_out:?}"
			report skipped "$1/${path}: over ${max_file_mb} MB" >&2
		fi
	done < <(GIT_INDEX_FILE="${index}" git -C "$1" diff --cached --name-only -z --diff-filter=AM HEAD)
	GIT_INDEX_FILE="${index}" git -C "$1" diff --cached --raw --diff-filter=A HEAD |
		awk -F '\t' '$1 ~ / 160000 / { print $2 }' | while IFS= read -r path; do
		echo "$1/${path}" >>"${nested:-/dev/null}"
		report nested "$1/${path}: a repository of its own; run wt sync inside it" >&2
	done
	tree="$(GIT_INDEX_FILE="${index}" git -C "$1" write-tree)"
	rm -f "${index}"
	git -C "$1" commit-tree "${tree}" -p HEAD -m "wip: uncommitted changes in $1"
}
