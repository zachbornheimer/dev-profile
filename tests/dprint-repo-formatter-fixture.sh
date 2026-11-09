#!/usr/bin/env bash
# The profile's dprint step runs on every commit in every repository, and dprint falls back to the
# profile's config (here: a dprint.jsonc in a parent directory, as ~/Developer/Personal/dprint.jsonc
# is for every checkout under it) when a repository carries none. A repository that formats with
# another tool (oxfmt, biome, prettier) and has no dprint config of its own must not be rewritten
# by that fallback: a tab-indented TypeScript file committed in such a repo turned a 90-line change
# into a 37,000-line diff. Run through git's real `git commit` with the profile's hk config:
#  1. A repo declaring oxfmt, biome or prettier and no dprint config commits its file byte-identical.
#  2. A repo with its own dprint config still has the file formatted.
#  3. A repo declaring no formatter at all still gets the profile's dprint (parent fallback).
# Only the dprint step runs, so another step's verdict cannot decide this fixture.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL dprint-repo-formatter: $*" >&2
	[[ ! -f "${scratch}/commit.txt" ]] || sed 's/^/  | /' "${scratch}/commit.txt" >&2
	exit 1
}

# Config-based hooks need git >= 2.36: take mise's pinned git when it manages one (Linux), else the
# PATH's (Homebrew on macOS), as tests/hook-path-free.sh does.
git_bin="$(mise which git 2>/dev/null || command -v git)"

# The profile's hk config, active the way bootstrap links it.
mkdir -p "${scratch}/hk-config"
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"

# The hook command home/gitconfig installs, with this checkout's bin directory in place of the
# installed one and only the dprint step judged.
command="$("${git_bin}" config --file "${repo}/home/gitconfig" --get hook.hk-pre-commit.command)"
profile_bin='${HOME}/.local/share/dev-profile/bin'
[[ "${command}" == *"${profile_bin}"* ]] || fail "home/gitconfig's hk-pre-commit command no longer names the profile bin directory"
command="${command//"${profile_bin}"/${repo}/bin} -S dprint"
command="${command//dev-profile-restore-tree-on-failure/${repo}/bin/dev-profile-restore-tree-on-failure}"
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

# The fallback: dprint looks upward from the repository, so the profile's config one directory
# above every scratch repository reaches all of them, as the real one does for ~/Developer/Personal.
cp "${repo}/config/dprint.jsonc" "${scratch}/dprint.jsonc"

tabbed_ts=$'export function f(x: number) {\n\tif (x) {\n\t\treturn x;\n\t}\n\treturn 0;\n}\n'
spaced_ts=$'export function f(x: number) {\n  if (x) {\n    return x;\n  }\n  return 0;\n}\n'

# base_commit <dir> <message>: a commit with no hook, so the fixture's own setup is not judged.
base_commit() {
	GIT_CONFIG_GLOBAL=/dev/null "${git_bin}" -C "$1" -c user.name=fixture -c user.email=fixture@example.invalid \
		-c commit.gpgsign=false commit -q -m "$2"
}

# new_repo <name> [config-file...]: a repository holding the given config files (a dprint one carries
# the profile's dprint config, any other is empty), base-committed
# with the hook off, and a staged tab-indented src/a.ts.
new_repo() {
	local cfg dir="${scratch}/$1"
	shift
	"${git_bin}" init -q -b main "${dir}"
	for cfg in "$@"; do
		mkdir -p "${dir}/$(dirname "${cfg}")"
		case "${cfg}" in
		*dprint.json*) cp "${repo}/config/dprint.jsonc" "${dir}/${cfg}" ;;
		*) printf '{}\n' >"${dir}/${cfg}" ;;
		esac
	done
	printf 'base\n' >"${dir}/README.txt"
	"${git_bin}" -C "${dir}" add -A
	base_commit "${dir}" "chore: base"
	mkdir -p "${dir}/src"
	printf '%s' "${tabbed_ts}" >"${dir}/src/a.ts"
	"${git_bin}" -C "${dir}" add src/a.ts
	printf '%s\n' "${dir}"
}

commit() { # <dir>: the real git commit, hooks on
	"${git_bin}" -C "$1" commit -q -m "feat: add a.ts" >"${scratch}/commit.txt" 2>&1
}

committed_ts() { "${git_bin}" -C "$1" show HEAD:src/a.ts; }

# 1. Another formatter is declared and no dprint config exists: the file is committed untouched.
for marker in .oxfmtrc.json .oxfmtrc.jsonc oxfmt.json biome.json biome.jsonc .prettierrc .prettierrc.json prettier.config.js; do
	dir="$(new_repo "other-${marker//[^a-z]/_}" "${marker}")"
	commit "${dir}" || fail "${marker}: a tab-indented TypeScript file must commit"
	[[ "$(committed_ts "${dir}")" == "${tabbed_ts%$'\n'}" ]] ||
		fail "${marker}: dprint must not rewrite a repo that declares another formatter, got: $(committed_ts "${dir}")"
	[[ "$(<"${dir}/src/a.ts")" == "${tabbed_ts%$'\n'}" ]] || fail "${marker}: the work tree file was rewritten"
done

# 2. The repository's own dprint config wins, even beside another formatter's config.
for dprint_cfg in dprint.json dprint.jsonc .dprint.json .dprint.jsonc .config/dprint.json; do
	dir="$(new_repo "own-${dprint_cfg//[^a-z]/_}" "${dprint_cfg}" .oxfmtrc.json)"
	commit "${dir}" || fail "${dprint_cfg}: a tab-indented TypeScript file must commit"
	[[ "$(committed_ts "${dir}")" == "${spaced_ts%$'\n'}" ]] ||
		fail "${dprint_cfg}: dprint must format a repo that has its own dprint config, got: $(committed_ts "${dir}")"
done

# 3. No formatter declared anywhere: the profile's dprint (the parent config) still formats.
dir="$(new_repo bare)"
commit "${dir}" || fail "bare: a tab-indented TypeScript file must commit"
[[ "$(committed_ts "${dir}")" == "${spaced_ts%$'\n'}" ]] ||
	fail "bare: dprint must keep formatting a repo that declares no formatter, got: $(committed_ts "${dir}")"

echo "ok dprint-repo-formatter"
