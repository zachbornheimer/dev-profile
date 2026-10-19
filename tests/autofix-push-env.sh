#!/usr/bin/env bash
# Shared setup for the autofix-push fixtures: real git, real hk, local bare remotes. Source it
# with the generated dir as $1; it defines the helpers below and leaves the cases to the caller.
# History is committed with the hooks off (HK=0), so its content reaches push unfixed.
set -euo pipefail

out="${1:?usage: <fixture> <generated-dir> [case...]}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
export style="style: apply profile fixes"
# The repo the running case works in, and the file it writes command output to.
repo=""
output=""

fail() {
	echo "FAIL ${FIXTURE:-autofix-push} fixture: $*" >&2
	[[ ! -f "${output}" ]] || sed 's/^/  | /' "${output}" >&2
	exit 1
}

# The generated hk config, active the way bootstrap links it; the hooks the way
# install-git-hooks writes them, with the commands this profile installs.
mkdir -p "${work}/hk-config"
ln -s "${out}/hk-config.pkl" "${work}/hk-config/config.pkl"
unset HK_FILE
export HK_CONFIG_DIR="${work}/hk-config"
export PATH="${out}/bin:${PATH}"
export GIT_CONFIG_GLOBAL="${work}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
git config --global user.name fixture
git config --global user.email fixture@example.com
git config --global commit.gpgsign false
install_hook() { # <event> <command>
	git config --global "hook.fixture-$1.event" "$1"
	git config --global "hook.fixture-$1.command" "test \"\${HK:-1}\" = \"0\" || $2"
}
install_hook pre-commit "${out}/bin/dev-profile-pre-commit"
install_hook post-commit "${out}/bin/dev-profile-post-commit"
install_hook commit-msg "hk run commit-msg"
install_hook pre-push "${out}/bin/dev-profile-pre-push"

# A repo whose "origin" is an empty bare repo; prints the repo path.
new_repo() { # <name>
	local dir="${work}/$1"
	git init -q --bare -b main "${dir}.git"
	git init -q -b main "${dir}"
	git -C "${dir}" remote add origin "${dir}.git"
	echo "${dir}"
}

# Unused imports (ruff F401) and a shebang script without its executable bit,
# committed with the hooks off.
commit_unfixed() {
	printf 'import os\nimport sys\n\nprint(sys.argv)\n' >app.py
	printf 'import os\n\nprint(2)\n' >util.py
	printf '#!/usr/bin/env bash\necho hi\n' >run.sh
	chmod 644 run.sh
	git add -A
	HK=0 git commit -q -m "feat: add app"
}

remote_git() { git --git-dir="${repo}.git" "$@"; }
no_git_noise() { ! grep -Eq '(fatal|warning):' "${output}" || fail "$1: git printed a fatal or a warning"; }

# Run the named cases in parallel, each in its own subshell with its own log; every
# case_<name> function sets $output and exits non-zero (through fail) on a miss.
run_cases() { # <case>...
	local name pids=() names=() index status=0
	for name in "$@"; do
		(
			set -euo pipefail
			"case_${name}"
		) >"${work}/case-${name}.log" 2>&1 &
		pids+=("$!")
		names+=("${name}")
	done
	for index in "${!pids[@]}"; do
		if ! wait "${pids[${index}]}"; then
			status=1
			echo "FAIL case ${names[${index}]}" >&2
			sed 's/^/  | /' "${work}/case-${names[${index}]}.log" >&2
		fi
	done
	return "${status}"
}
