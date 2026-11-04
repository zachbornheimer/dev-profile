#!/usr/bin/env bash
# On an unowned repository (e.g. can1357/oh-my-pi), hk pre-commit and pre-push
# follow the repository's own formatter/linter configs (.oxfmtrc.json, repo-local
# dprint/markdownlint/yamllint) instead of applying the personal global defaults.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL unowned-repo-conventions: $*" >&2
	[[ ! -f "${scratch}/out.txt" ]] || sed 's/^/  | /' "${scratch}/out.txt" >&2
	exit 1
}

git_bin="$(mise which git)"
export PATH="${repo}/bin:${PATH}"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid

# 1. dev-profile-repo-owned classifies owned vs external remotes and forks.
owned_repo="${scratch}/owned"
"${git_bin}" init -q -b main "${owned_repo}"
"${git_bin}" -C "${owned_repo}" remote add origin "https://github.com/Software-Automation-Holdings-LLC/isa-platform.git"
(cd "${owned_repo}" && dev-profile-repo-owned) || fail "SAH repo must be classified as owned"

# gh answers over the network, which a checkout that was never authenticated cannot rely on: it
# prints the HTTP error body on stdout and exits non-zero. That body is not an owner, so the
# classification must not follow it — this is the CI case, where the actions token cannot read an
# org repo. Stub gh into that state, with no cached answer, and require the remote to decide.
gh_stub="${scratch}/gh-stub"
mkdir -p "${gh_stub}"
cat >"${gh_stub}/gh" <<'GHEOF'
#!/usr/bin/env bash
printf '%s\n' '{"message":"Not Found","documentation_url":"https://docs.github.com/rest/repos/repos#get-a-repository","status":"404"}'
exit 1
GHEOF
chmod +x "${gh_stub}/gh"
stub_path="${gh_stub}:${PATH}"
rm -f "${owned_repo}/.git/dev-profile-effective-owner"
if ! (cd "${owned_repo}" && PATH="${stub_path}" dev-profile-repo-owned); then
	fail "an owned repo whose gh cannot read it must stay owned"
fi

# A clone whose cache file holds that same error body (written by a profile that trusted gh's
# output) must not inherit the answer.
printf '%s\n' '{"message":"Not Found","status":"404"}' >"${owned_repo}/.git/dev-profile-effective-owner"
if ! (cd "${owned_repo}" && PATH="${stub_path}" dev-profile-repo-owned); then
	fail "a poisoned owner cache must not classify an owned repo as unowned"
fi
rm -f "${owned_repo}/.git/dev-profile-effective-owner"

unowned_repo="${scratch}/unowned"
"${git_bin}" init -q -b main "${unowned_repo}"
"${git_bin}" -C "${unowned_repo}" remote add origin "https://github.com/can1357/oh-my-pi.git"
if (cd "${unowned_repo}" && dev-profile-repo-owned); then
	fail "can1357/oh-my-pi must be classified as unowned"
fi

fork_repo="${scratch}/fork"
"${git_bin}" init -q -b main "${fork_repo}"
"${git_bin}" -C "${fork_repo}" remote add origin "https://github.com/zachbornheimer/oh-my-pi.git"
"${git_bin}" -C "${fork_repo}" remote add upstream "https://github.com/can1357/oh-my-pi.git"
if (cd "${fork_repo}" && dev-profile-repo-owned); then
	fail "a fork whose upstream is can1357/oh-my-pi must be classified as unowned"
fi

# 2. Unowned repo with .oxfmtrc.json and no dprint/markdownlint/yamllint config:
#    - parent dprint.jsonc in scratch directory must NOT format JSON or Markdown in unowned_repo
#    - markdownlint-fix and markdownlint must NOT rewrite or reject duplicate CHANGELOG headings
#    - repo-local oxfmt formats staged TypeScript files
#    - ban-trunk-prettier does not reject .prettierrc in an unowned repo
cp "${repo}/config/dprint.jsonc" "${scratch}/dprint.jsonc"
echo '{"useTabs": true}' >"${unowned_repo}/.oxfmtrc.json"
mkdir -p "${unowned_repo}/node_modules/.bin" "${unowned_repo}/src"
cat >"${unowned_repo}/node_modules/.bin/oxfmt" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "--check" ]]; then
	shift
	for f in "$@"; do
		grep -q $'^\t' "$f" || exit 1
	done
	exit 0
fi
for f in "$@"; do
	sed 's/^  /\t/' "$f" >"$f.tmp" && mv "$f.tmp" "$f"
done
EOF
chmod +x "${unowned_repo}/node_modules/.bin/oxfmt"

printf '{"a":   1}\n' >"${unowned_repo}/data.json"
cat >"${unowned_repo}/CHANGELOG.md" <<'EOF'
# Changelog

## [1.1.0]

### Added

- first

## [1.0.0]

### Added

- second
EOF
printf 'export function f() {\n  return 1;\n}\n' >"${unowned_repo}/src/a.ts"

(
	cd "${unowned_repo}"
	dev-profile-format fmt data.json CHANGELOG.md src/a.ts >"${scratch}/out.txt" 2>&1 || fail "dev-profile-format fmt failed on unowned repo"
	[[ "$(<data.json)" == '{"a":   1}' ]] || fail "unowned repo without dprint config had its JSON rewritten by parent dprint.jsonc: $(<data.json)"
	grep -q $'^\treturn 1;' src/a.ts || fail "unowned repo with .oxfmtrc.json did not format src/a.ts with oxfmt"
	dev-profile-format check data.json CHANGELOG.md src/a.ts >"${scratch}/out.txt" 2>&1 || fail "dev-profile-format check failed after oxfmt"
	dev-profile-markdownlint --fix CHANGELOG.md >"${scratch}/out.txt" 2>&1 || fail "dev-profile-markdownlint --fix failed on unowned repo"
	dev-profile-markdownlint CHANGELOG.md >"${scratch}/out.txt" 2>&1 || fail "dev-profile-markdownlint check failed on unowned repo without .markdownlintrc"
	echo '{}' >.prettierrc
	"${git_bin}" add -A
	"${git_bin}" -c commit.gpgsign=false commit -qm "feat: initial"
	dev-profile-ban-trunk-prettier >"${scratch}/out.txt" 2>&1 || fail "ban-trunk-prettier must not reject .prettierrc in an unowned repo"
)

echo "ok unowned-repo-conventions"
