#!/usr/bin/env bash
# The gate for this config: load the real init.lua headlessly through
# $XDG_CONFIG_HOME/nvim and assert the behavior described in LAYOUT.md.
#
#   ./test/run.sh                                   # this worktree / checkout
#   NVIM_TEST_CONFIG=~/.config/nvim ./test/run.sh    # any other config dir
set -uo pipefail

root=${NVIM_TEST_CONFIG:-$(cd "$(dirname "$0")/.." && pwd)}
checks=${NVIM_TEST_CHECKS:-$root/test/checks.lua}
# Fail closed: an error in the probe must exit non-zero, never wait for input.
probe="lua vim.schedule(function() local ok, err = pcall(dofile, '$checks'); if not ok then vim.api.nvim_err_writeln('PROBE ERROR: ' .. tostring(err)); vim.cmd('cquit 1') end end)"
limit=${NVIM_TEST_TIMEOUT:-120}

# Resolve mktemp's /var symlink: snacks' bigfile check compares the detected
# path against the buffer name and refuses mismatches.
tmp=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$tmp"' EXIT

# nvim resolves its config as $XDG_CONFIG_HOME/nvim, so a symlink is enough to
# reach init.lua exactly as the editor does. Plugins/state stay shared.
ln -s "$root" "$tmp/nvim"
export XDG_CONFIG_HOME="$tmp"

project="$tmp/project"
mkdir -p "$project"
printf 'hello from the fixture\n' >"$project/file.txt"
printf 'a second fixture\n' >"$project/other.txt"
head -c 2000000 /dev/zero | tr '\0' 'x' >"$tmp/big.txt"
export CHECK_FILE="$project/file.txt"

# A real unmerged file: git-conflict only reports files git itself lists as
# conflicted. The global git config is blanked so commit signing cannot prompt.
conflict="$tmp/conflict"
mkdir -p "$conflict"
(
	cd "$conflict" || exit 1
	export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
	git() { command git -c user.name=fixture -c user.email=fixture@example.com "$@"; }
	git init -q -b main
	printf 'base\n' >f.txt && git add f.txt && git commit -qm base
	git checkout -qb side && printf 'side\n' >f.txt && git commit -qam side
	git checkout -q main && printf 'main\n' >f.txt && git commit -qam main
	git merge side >/dev/null 2>&1
	true
)
if [ -z "$(git -C "$conflict" ls-files -u)" ]; then
	echo "fixture: merge produced no conflict" >&2
	exit 1
fi

failed=0

report() { # report <scenario> <status> <output>
	local asserts
	asserts=$(printf '%s\n' "$3" | grep -o 'PASS ' | wc -l | tr -d ' ')
	if [ "$2" -eq 0 ]; then
		printf 'ok   %-10s %s asserts\n' "$1" "$asserts"
	else
		printf 'FAIL %-10s exit=%s\n%s\n' "$1" "$2" "$3"
		failed=1
	fi
}

run() { # run <scenario> <cwd> <nvim args...>
	local scenario=$1 cwd=$2
	shift 2
	local out status
	out=$(cd "$cwd" && CHECK_SCENARIO="$scenario" timeout "$limit" nvim --headless "$@" -c "$probe" </dev/null 2>&1)
	status=$?
	report "$scenario" "$status" "$out"
}

# Preflight: a config that cannot load makes every scenario meaningless.
out=$(cd "$tmp" && timeout "$limit" nvim --headless -c "qall!" </dev/null 2>&1)
report load $? "$out"

run config "$project" "$project/file.txt"
run colors "$project" "$project/file.txt"
run file "$project" "$project/file.txt"
run gitcommit "$project" "$project/file.txt" -c 'setlocal filetype=gitcommit'
run directory "$project" "$project"
run bigfile "$tmp" "$tmp/big.txt"
run home "$HOME" "$project/file.txt"
# The herdr one-shot popup edits its prompt in nvim with the explorer opted out.
NVIM_NO_EXPLORER=1 run oneshot "$project" "$project/file.txt"
# learn-launch is an extensionless uv script. Nvim's # fallback calls it conf
# unless the shebang plus the PEP 723 block identify it as Python.
printf '%s\n' '#!/usr/bin/env -S uv run --script' '# /// script' '# requires-python = ">=3.10"' '# ///' 'print(1)' >"$tmp/learn-launch"
run uvscript "$tmp" "$tmp/learn-launch"
# An explicit launch can name the syntax even when detection would say otherwise.
NVIM_FILETYPE=python run envft "$project" "$project/file.txt"
CHECK_FILE="$conflict/f.txt" HERDR_ENV=1 run plugins "$conflict" "$conflict/f.txt"
# Outside a herdr pane the annotation half of herdr-nvim must not load.
CHECK_FILE="$conflict/f.txt" HERDR_ENV= run no-herdr "$conflict" "$conflict/f.txt"

# A stdin pipe is a special buffer: the explorer must stay out of the way.
out=$(cd "$tmp" && CHECK_SCENARIO=stdin timeout "$limit" nvim --headless -c "$probe" <"$project/file.txt" 2>&1)
report stdin $? "$out"

if [ "$failed" -ne 0 ]; then
	echo "gate: FAILED"
	exit 1
fi
echo "gate: passed"
