#!/usr/bin/env bash
set -euo pipefail
# Edit tools/repo/ban-trunk-prettier.sh: `mise run generate` copies it into bin/.
# Push guard: an add or modify, in the commits being pushed, of trunk or prettier config fails. Deleting stays allowed.
banned_file='(^|/)(\.trunk/|\.prettierrc[^/]*$|prettier\.config\.[^/]*$|\.prettierignore$)'
# Added lines only: removing a dependency or tool line must pass.
banned_package_line='^\+.*"(prettier|@prettier/[^"]*)"[[:space:]]*:'
banned_mise_line='^\+[[:space:]]*"?[^=]*\b(prettier|trunk)\b[^=]*"?[[:space:]]*='
base="$(git merge-base HEAD origin/HEAD 2>/dev/null || git hash-object -t tree /dev/null)"
failed=0
while IFS= read -r path; do
	[[ -n "${path}" ]] || continue
	if [[ "${path}" =~ ${banned_file} ]]; then
		echo "banned: ${path}" >&2
		failed=1
		continue
	fi
	case "${path}" in
	package.json | */package.json) pattern="${banned_package_line}" ;;
	mise.toml | */mise.toml | .mise*.toml | */.mise*.toml | mise.*.toml | */mise.*.toml | */mise/*.toml) pattern="${banned_mise_line}" ;;
	*) continue ;;
	esac
	if git diff -U0 --no-color "${base}" HEAD -- "${path}" | grep -Eq "${pattern}"; then
		echo "banned: ${path} adds trunk or prettier" >&2
		failed=1
	fi
done < <(git diff --name-only --diff-filter=ACMRT "${base}" HEAD)
if [[ "${failed}" -ne 0 ]]; then
	echo "trunk and prettier are banned on this machine. Use dprint via mise (system config ~/Developer/Personal/dprint.jsonc); delete the files instead." >&2
	exit 1
fi
