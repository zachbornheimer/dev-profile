#!/usr/bin/env bash
# A fresh worktree of a narrow clone looks ready and is not. Its fetch refspec
# names one branch, so a branch pushed upstream has no local tracking ref and a
# branch deleted upstream stays advertised; and a checkout that declares a
# package has no node_modules until someone installs it. dev-profile-worktree-copy
# must leave both fixed: the tracking ref stored and the deleted one pruned, and
# the declared dependency installed from the lockfile, without touching a
# checkout that declares nothing. `wt` and `bun` are stubs, so no worktrunk or
# network is needed; the remote is a local bare repo.
# Usage: worktree-readiness-fixture.sh <repo-root>
set -euo pipefail
repo="${1:?usage: worktree-readiness-fixture.sh <repo-root>}"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL worktree-readiness: $*" >&2
	exit 1
}

git_bin=""
for candidate in /usr/bin/git /opt/homebrew/bin/git; do
	[[ -x "${candidate}" ]] && git_bin="${candidate}" && break
done
[[ -n "${git_bin}" ]] || fail "no real git binary"

stub_bin="${scratch}/stub-bin"
mkdir -p "${stub_bin}"
ln -s "${git_bin}" "${stub_bin}/git"
cat >"${stub_bin}/wt" <<'EOF'
#!/usr/bin/env bash
# The copy this stands in for reflinks ignored files; the fixture has none.
[[ "${1:-} ${2:-}" == "step copy-ignored" ]] && exit 0
echo "unexpected wt call: $*" >&2
exit 1
EOF
# Records the install it was asked for and lands the package the lockfile pins,
# so the fixture can see that the declared dependency arrived and nothing else.
cat >"${stub_bin}/bun" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${BUN_LOG}"
if [[ "$*" == "install --frozen-lockfile" ]]; then
	mkdir -p node_modules/e2b
	printf '{}\n' >node_modules/e2b/package.json
fi
exit "${STUB_BUN_STATUS:-0}"
EOF
chmod +x "${stub_bin}/wt" "${stub_bin}/bun"
export PATH="${stub_bin}:${repo}/bin:${PATH}"
export GIT_CONFIG_SYSTEM=/dev/null
export GIT_CONFIG_GLOBAL="${scratch}/gitconfig"
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
export BUN_LOG="${scratch}/bun.log"
printf '[core]\n\texcludesFile = %s\n' "${scratch}/global-ignore" >"${GIT_CONFIG_GLOBAL}"
printf '.DS_Store\nnode_modules/\n' >"${scratch}/global-ignore"

remote="${scratch}/remote"
"${git_bin}" init -q --bare -b main "${remote}"
src="${scratch}/src"
"${git_bin}" clone -q "${remote}" "${src}"
(
	cd "${src}"
	"${git_bin}" -c commit.gpgsign=false commit -qm init --allow-empty
	"${git_bin}" branch -M main
	"${git_bin}" push -q origin main
	"${git_bin}" checkout -q -b old
	"${git_bin}" -c commit.gpgsign=false commit -qm old --allow-empty
	"${git_bin}" push -q -u origin old
	"${git_bin}" push -q origin --delete old
	"${git_bin}" checkout -q -b relay/test main
	"${git_bin}" -c commit.gpgsign=false commit -qm work --allow-empty
	"${git_bin}" push -q -u origin relay/test
)

# The defect shape: a clone whose fetch refspec names only main, still holding
# a tracking ref for the branch that was deleted upstream.
narrow="${scratch}/narrow"
"${git_bin}" clone -q --single-branch --branch main "${remote}" "${narrow}"
"${git_bin}" -C "${narrow}" update-ref refs/remotes/origin/old HEAD
printf '{}\n' >"${narrow}/package.json"
printf '{}\n' >"${narrow}/bun.lock"
"${git_bin}" -C "${narrow}" add package.json bun.lock
"${git_bin}" -C "${narrow}" -c commit.gpgsign=false commit -qm "chore: declare the package"

refspec_before="$("${git_bin}" -C "${narrow}" config --get-all remote.origin.fetch)"
[[ "${refspec_before}" == "+refs/heads/main:refs/remotes/origin/main" ]] ||
	fail "the fixture must start from a single-branch refspec (got ${refspec_before})"
"${git_bin}" -C "${narrow}" rev-parse --verify -q refs/remotes/origin/old >/dev/null ||
	fail "the fixture must start with the deleted branch still advertised"
"${git_bin}" -C "${narrow}" rev-parse --verify -q refs/remotes/origin/relay/test >/dev/null &&
	fail "the fixture must start without a tracking ref for the ticket branch"

start="${SECONDS}"
(cd "${narrow}" && dev-profile-worktree-copy) || fail "dev-profile-worktree-copy failed"
elapsed=$((SECONDS - start))

refspec_after="$("${git_bin}" -C "${narrow}" config --get-all remote.origin.fetch)"
[[ "${refspec_after}" == "+refs/heads/*:refs/remotes/origin/*" ]] ||
	fail "the fetch refspec must cover every branch (got ${refspec_after})"
"${git_bin}" -C "${narrow}" rev-parse --verify -q refs/remotes/origin/relay/test >/dev/null ||
	fail "the ticket branch must have a stored tracking ref"
"${git_bin}" -C "${narrow}" rev-parse --verify -q refs/remotes/origin/old >/dev/null &&
	fail "the deleted branch must be pruned"
[[ -f "${narrow}/node_modules/e2b/package.json" ]] ||
	fail "the declared dependency must be installed"
grep -qxF "install --frozen-lockfile" "${BUN_LOG}" ||
	fail "the install must keep the lockfile"
[[ "${elapsed}" -lt 30 ]] || fail "readiness took ${elapsed}s; it must stay inside the hook bound"

# A checkout that declares nothing gets no install.
bare="${scratch}/bare"
"${git_bin}" clone -q "${remote}" "${bare}"
: >"${BUN_LOG}"
(cd "${bare}" && dev-profile-worktree-copy) || fail "a checkout that declares nothing must still succeed"
[[ ! -s "${BUN_LOG}" ]] || fail "a checkout that declares nothing must not be installed"

# A checkout that already holds its dependencies is not installed again.
: >"${BUN_LOG}"
(cd "${narrow}" && dev-profile-worktree-copy) || fail "a second run must succeed"
[[ ! -s "${BUN_LOG}" ]] || fail "a checkout that already holds its dependencies must not be reinstalled"

# A package declared two levels down, beside a setup task that is not an
# install, still gets installed, and the setup task still runs.
mkdir -p "${narrow}/cloudflare/relay-edge"
rm -rf "${narrow}/node_modules"
mv "${narrow}/package.json" "${narrow}/bun.lock" "${narrow}/cloudflare/relay-edge/"
printf '[tasks.setup]\nrun = "true"\n' >"${narrow}/mise.toml"
cat >"${stub_bin}/mise" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-} ${2:-}" == "tasks ls" ]]; then
	printf '%s\n' '[{"name":"setup"}]'
	exit 0
fi
if [[ "${1:-} ${2:-}" == "run setup" ]]; then
	printf '%s\n' "run setup" >>"${MISE_LOG}"
	exit 0
fi
echo "unexpected mise call: $*" >&2
exit 1
EOF
chmod +x "${stub_bin}/mise"
export MISE_LOG="${scratch}/mise.log"
: >"${BUN_LOG}"
: >"${MISE_LOG}"
(cd "${narrow}" && dev-profile-worktree-copy) || fail "a nested package must still be prepared"
[[ -f "${narrow}/cloudflare/relay-edge/node_modules/e2b/package.json" ]] ||
	fail "a package declared two levels down must be installed"
grep -qxF "run setup" "${MISE_LOG}" || fail "the declared setup task must still run"

echo "ok worktree-readiness (${elapsed}s)"
