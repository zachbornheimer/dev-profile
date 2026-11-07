#!/usr/bin/env bash
# The trunk/prettier push guard judges only what the pushed commits add, so a
# prettier dependency the remote default branch already carries passes, even in a
# reused clone that has no refs/remotes/origin/HEAD.
# Usage: ban-trunk-prettier-fixture.sh [helper]   (default: this repo's bin/dev-profile-ban-trunk-prettier)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
helper="${1:-${root}/bin/dev-profile-ban-trunk-prettier}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL ban-trunk-prettier fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com

run_helper() { "${helper}" >"${work}/output.txt" 2>&1; }
expect_pass() { run_helper || fail "$1"; }
expect_fail() {
	if run_helper; then fail "$1"; fi
	grep -Fq "banned: package.json adds a retired formatter or hook runner" "${work}/output.txt" || fail "$1: the failure must name package.json"
}

package_json() { # <version> [extra dependency line]
	printf '{\n  "name": "app",\n  "version": "%s",\n  "devDependencies": {\n    "prettier": "^3.0.0"%s\n  }\n}\n' "$1" "${2:-}"
}

# A remote whose default branch already depends on prettier.
origin="${work}/origin.git"
git init -q --bare -b main "${origin}"
seed="${work}/seed"
git clone -q "${origin}" "${seed}" 2>/dev/null
(
	cd "${seed}"
	git config commit.gpgsign false
	package_json 1.0.0 >package.json
	echo base >README.md
	git add -A && git commit -qm base && git push -q origin HEAD:main
)

new_clone() { # <name>: a clone on a feature branch with origin/HEAD deleted
	git clone -q "${origin}" "${work}/$1" 2>/dev/null
	cd "${work}/$1"
	git config commit.gpgsign false
	git remote set-head origin -d >/dev/null
	git rev-parse -q --verify refs/remotes/origin/HEAD >/dev/null && fail "origin/HEAD must be gone in $1"
	git switch -q -c feature
}

# 1. No origin/HEAD; the push does not touch prettier.
new_clone reused
echo more >>README.md
git commit -qam "unrelated"
expect_pass "a commit that leaves the existing prettier dependency alone must pass without origin/HEAD"

# 2. Same, and the push edits package.json elsewhere.
package_json 1.0.1 >package.json
git commit -qam "bump version"
expect_pass "a package.json edit that keeps the existing prettier line must pass without origin/HEAD"

# 3. Adding a second prettier-family dependency in the push still fails.
package_json 1.0.1 ',
    "@prettier/plugin-xml": "^3.0.0"' >package.json
git commit -qam "add a prettier plugin"
expect_fail "adding a prettier dependency must fail without origin/HEAD"

# 4. A pushed prettier config file fails.
git reset -q --hard HEAD~1
echo '{}' >.prettierrc
git add .prettierrc && git commit -qm "prettierrc"
if run_helper; then fail "a pushed .prettierrc must fail without origin/HEAD"; fi
grep -Fq "banned: .prettierrc" "${work}/output.txt" || fail "the failure must name .prettierrc"

# 5. Only a non-default remote branch exists (no origin/HEAD, main, master).
new_clone other-branch
git branch -q -m feature topic
git update-ref -d refs/remotes/origin/main
git update-ref refs/remotes/origin/trunk-x "$(git rev-parse HEAD)"
echo more >>README.md
git commit -qam "unrelated"
expect_pass "the first remote branch the commits descend from is the base"

# 6. The remote copy of the pushed branch is the base, found through SAH_PUSH_REFS.
new_clone pushed-ref
git update-ref -d refs/remotes/origin/main
echo more >>README.md
git commit -qam "unrelated"
tip="$(git rev-parse HEAD)"
git update-ref refs/remotes/origin/feature "${tip}~1"
printf 'refs/heads/feature %s refs/heads/feature %s\n' "${tip}" "$(git rev-parse "${tip}~1")" >"${work}/refs"
SAH_PUSH_REFS="${work}/refs" run_helper || fail "the remote tip of the pushed ref must serve as the base"
package_json 1.0.2 ',
    "@prettier/plugin-xml": "^3.0.0"' >package.json
git commit -qam "add a prettier plugin"
printf 'refs/heads/feature %s refs/heads/feature %s\n' "$(git rev-parse HEAD)" "${tip}" >"${work}/refs"
if SAH_PUSH_REFS="${work}/refs" run_helper; then fail "a prettier dependency added after the remote tip must fail"; fi

# 7. A repository with no remote history at all diffs from the empty tree.
git init -q -b main "${work}/local"
cd "${work}/local"
git config commit.gpgsign false
package_json 1.0.0 >package.json
git add -A && git commit -qm "first"
expect_fail "with no remote history every prettier dependency counts as added"

# 8. The other retired formatters (biome, oxfmt) and hook runners (lefthook, husky,
#    lint-staged, simple-git-hooks, the pre-commit framework) fail like trunk and
#    prettier, by config file, package.json line and mise tool line. oxlint is a linter and stays.
new_clone retired-tools
for path in biome.json biome.jsonc .biome.json .oxfmtrc.json .oxfmtrc.jsonc oxfmt.json oxfmt.config.ts \
	lefthook.yml .lefthook.yaml lefthook-local.yml lefthook.json .husky/pre-commit .lintstagedrc.json \
	lint-staged.config.mjs .simple-git-hooks.json simple-git-hooks.config.js .pre-commit-config.yaml sub/dir/biome.json; do
	mkdir -p "$(dirname "${path}")"
	echo '{}' >"${path}"
	git add -A && git commit -qm "add ${path}"
	if run_helper; then fail "a pushed ${path} must fail"; fi
	grep -Fq "banned: ${path}" "${work}/output.txt" || fail "the failure must name ${path}"
	git reset -q --hard HEAD~1
done
echo '{}' >.oxlintrc.json
git add -A && git commit -qm "oxlint config"
expect_pass "an oxlint config is a linter and must pass"
git reset -q --hard HEAD~1

for line in '"husky": "^9.0.0"' '"lint-staged": {}' '"@biomejs/biome": "^1.0.0"' '"oxfmt": "^0.1.0"' \
	'"simple-git-hooks": {}' '"lefthook": "^1.0.0"' '"prepare": "husky"' '"precommit": "lint-staged"'; do
	package_json 1.0.1 ",
    ${line}" >package.json
	git commit -qam "add ${line}"
	expect_fail "adding ${line} to package.json must fail"
	git reset -q --hard HEAD~1
done

for line in 'lefthook = "latest"' '"npm:husky" = "latest"' 'biome = "latest"' '"pipx:pre-commit" = "latest"' 'oxfmt = "latest"'; do
	printf '[tools]\n%s\n' "${line}" >mise.toml
	git add mise.toml && git commit -qm "add ${line}"
	if run_helper; then fail "adding ${line} to mise.toml must fail"; fi
	grep -Fq "banned: mise.toml adds a retired formatter or hook runner" "${work}/output.txt" || fail "the failure must name mise.toml for ${line}"
	git reset -q --hard HEAD~1
done
printf '[tools]\nhk = "latest"\ndprint = "latest"\noxlint = "latest"\n\n[tasks.pre-commit]\nrun = "hk run pre-commit"\n' >mise.toml
git add mise.toml && git commit -qm "hk and dprint"
expect_pass "hk, dprint, oxlint and a pre-commit task name must pass"

echo "ban-trunk-prettier fixture ok"
