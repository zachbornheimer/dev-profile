#!/usr/bin/env bash
# The pre-commit hook, run by git's real `git commit` through the hook command in
# home/gitconfig, with the profile's hk and dprint config. Three promises:
#  1. A commit holding no files passes: hk hands a glob-less step an empty {{files}} and
#     `hk util` exits with a usage error.
#  2. A tab-indented TypeScript file commits byte for byte: a global dprint config must not
#     rewrite the formatting a repository owns. JSON, which the config does own, still formats.
#  3. A commit whose hook chain fails changes nothing: the fix steps ran and edited the
#     staged files, and the work tree and index come back exactly as they were. Without the
#     restore, the author's edits were replaced by the fixers' output.
# Only the steps this fixture judges run, so another step's verdict cannot decide it.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL pre-commit: $*" >&2
	[[ ! -f "${scratch}/commit.txt" ]] || sed 's/^/  | /' "${scratch}/commit.txt" >&2
	exit 1
}

# Config-based hooks need the profile's pinned git; the system git ignores them.
git_bin="$(mise which git)"
work="${scratch}/work"

# The profile's hk config, active the way bootstrap links it.
mkdir -p "${scratch}/hk-config"
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"

# The hook command is the one home/gitconfig installs, with this checkout's bin directory in
# place of the installed one and the judged steps appended.
command="$("${git_bin}" config --file "${repo}/home/gitconfig" --get hook.hk-pre-commit.command)"
[[ "${command}" == *'${HOME}/.local/share/dev-profile/bin'* ]] || fail "home/gitconfig's hk-pre-commit command no longer names the profile bin directory"
profile_bin='${HOME}/.local/share/dev-profile/bin'
command="${command//"${profile_bin}"/${repo}/bin} -S newlines -S trailing-whitespace -S dprint -S stylelint -S no-commit-to-branch"
cat >"${scratch}/gitconfig" <<EOF
[user]
	name = fixture
	email = fixture@example.invalid
[commit]
	gpgsign = false
EOF
"${git_bin}" config --file "${scratch}/gitconfig" hook.hk-pre-commit.event pre-commit
"${git_bin}" config --file "${scratch}/gitconfig" hook.hk-pre-commit.command "${command}"
export HK_CONFIG_DIR="${scratch}/hk-config" GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
unset HK HK_FILE

git() { "${git_bin}" -C "${work}" "$@"; }
# dprint reads the profile's config from the repository root, like a checkout that has one.
"${git_bin}" init -q -b main "${work}"
cp "${repo}/config/dprint.jsonc" "${work}/dprint.jsonc"
printf 'dprint.jsonc\n' >"${work}/.gitignore"
mkdir "${work}/src"
git remote add origin https://example.invalid/repo.git

commit() { # <message> [git commit args]: the real git commit, hooks on
	local message="$1"
	shift
	git commit -q -m "${message}" "$@" >"${scratch}/commit.txt" 2>&1
}

# 1. Initial commit on unborn main with an origin configured: no-commit-to-branch must allow it,
# and a commit holding no files must pass.
commit "chore: empty" --allow-empty || fail "initial commit on unborn main with origin must pass the hook"
! grep -q 'required arguments were not provided' "${scratch}/commit.txt" ||
	fail "an empty file list reached an hk util step"

# 1b. Subsequent direct commit on main with an origin configured must be blocked with a helpful message,
# then switch to a feature branch for the remaining cases.
if commit "chore: second on main" --allow-empty; then
	fail "a second direct commit on main with origin must be blocked by no-commit-to-branch"
fi
grep -qF "wt commit-unstaged" "${scratch}/commit.txt" ||
	fail "no-commit-to-branch error must mention 'wt commit-unstaged'"
git switch -q -c feat/test
# 2. A tab-indented TypeScript file commits unchanged; JSON is still formatted.
printf 'export function f(x: number) {\n\tif (x) {\n\t\treturn x;\n\t}\n\treturn 0;\n}\n' >"${work}/src/a.ts"
printf '{"a":   1}\n' >"${work}/data.json"
want_ts="$("${git_bin}" hash-object "${work}/src/a.ts")"
git add src/a.ts data.json
commit "feat: add files" || fail "a clean tab-indented TypeScript file must commit"
[[ "$(git rev-parse HEAD:src/a.ts)" == "${want_ts}" ]] || fail "the hook rewrote the TypeScript file the repository committed"
[[ "$(git show HEAD:data.json)" == '{ "a": 1 }' ]] || fail "dprint must still format JSON, got: $(git show HEAD:data.json)"

# 3. A failing chain: a.ts holds a staged trailing-space edit plus a further unstaged edit, and
# bad.json is not JSON, so the dprint step fails after the whitespace fixer has rewritten a.ts.
printf 'export function f(x: number) {   \n\tif (x) {\n\t\treturn x;\n\t}\n\treturn 0;\n}\n' >"${work}/src/a.ts"
printf ':root {\n  --x: 1;\n}\n' >"${work}/src/a.css"
printf '{"a": ' >"${work}/bad.json"
git add src/a.ts src/a.css bad.json
printf 'export const unstaged = 1;\n' >>"${work}/src/a.ts"

tree_state() {
	{
		git diff
		echo --cached
		git diff --cached
		echo --index
		git ls-files -s
		echo --files
		shasum "${work}/src/a.ts" "${work}/src/a.css" "${work}/bad.json"
		git status --porcelain
	} | shasum
}
head_before="$(git rev-parse HEAD)"
state_before="$(tree_state)"
if commit "feat: must not land"; then fail "the dprint step must fail on bad.json, or this case proves nothing"; fi
grep -Eq 'trailing-whitespace – [0-9]+ files? modified' "${scratch}/commit.txt" ||
	fail "the whitespace fixer must have edited the staged files, or this case proves nothing"
! grep -qF 'ConfigurationError' "${scratch}/commit.txt" ||
	fail "stylelint without a repo config must not dump ConfigurationError to stderr when another step fails"
[[ "$(git rev-parse HEAD)" == "${head_before}" ]] || fail "a failed hook still made a commit"
[[ "$(tree_state)" == "${state_before}" ]] || fail "a failed commit changed the work tree or the index"

echo "ok pre-commit"
