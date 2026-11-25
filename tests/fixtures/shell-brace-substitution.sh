#!/usr/bin/env bash
exclude_copied_output() { # <primary-worktree> <this-worktree>
	local primary="$1" current="$2" entry path git_dir excludes inherited ignored patterns
	patterns=()
	# Every candidate path is collected first, then asked about in one
	# check-ignore call. A call per path spawned a process per copied directory
	# (about 130 on a heavy checkout), and a spawn can stall on a loaded machine;
	# `--stdin` answers all of them from a single process, printing only the
	# paths this branch already ignores.
	candidates="$({
		while IFS= read -r -d '' entry; do
			[[ "${entry:0:2}" == '!!' ]] || continue # not ignored in the primary
			path="${entry:3}"
			[[ -n "${path}" && "${path}" != *$'\n'* && -e "${current}/${path}" ]] || continue # the copy did not land it here
			printf '%s\n' "${path}"
		done < <(git -C "${primary}" status --porcelain --ignored -z)
	})"
	[[ -n "${candidates}" ]] || return 0
	ignored="$(printf '%s\n' "${candidates}" | git check-ignore --stdin 2>/dev/null || :)"
	while IFS= read -r path; do
		[[ -n "${path}" ]] || continue
		if [[ -n "${ignored}" ]]; then
			case $'\n'"${ignored}"$'\n' in
			*$'\n'"${path}"$'\n'*) continue ;; # this branch's rules cover it
			esac
		fi
		patterns+=("/${path}")
	done <<<"${candidates}"
	((${#patterns[@]})) || return 0
}
