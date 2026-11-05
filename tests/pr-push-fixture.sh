#!/usr/bin/env bash
# `wt pr` must publish through its own pre-push gate. dev-profile-pr pushed
# `HEAD:refs/heads/<branch>` unconditionally, so on a branch whose remote was
# already current (pushed once, PR still to publish) the push updated nothing:
# git still runs the pre-push hook for an up-to-date push and hands it zero
# ref lines, which the gate read as "no readable push refs" and refused, so
# `wt pr` died at its own push and never reached `gh pr create`. This fixture
# drives the real dev-profile-pr through the real dev-profile-pre-push gate:
# a first publish of a branch one commit ahead of its base must be judged (not
# waved through) and advance the remote ref; a publish over the now-current
# remote must reach `gh pr create` (or reuse the open PR) instead of dying at
# the push; and the default-branch refusal still refuses.
# Real git; gh, wt, kitten and the notifiers are stubs that log their arguments.
set -euo pipefail
# The profile tree is this script's own repository: doctor and the pool run it
# from here, and a caller-supplied path would copy scripts from anywhere.
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL pr-push fixture: $*" >&2
	[[ ! -f "${work}/run.txt" ]] || sed 's/^/  | /' "${work}/run.txt" >&2
	exit 1
}

stubs="${work}/stubs"
state="${work}/state"
mkdir -p "$stubs" "$state"
export PR_STATE="$state" PR_LOG="${work}/log"

# gh answers with what the real command prints after its --jq filter.
cat >"${stubs}/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >>"${PR_LOG}"
# Every call that works on a repo must name it; gh alone prefers a fork's parent.
if [[ "$1" == pr && "$*" != *" --repo me/repo" ]]; then
	echo "FAIL gh stub: no --repo: $*" >&2
	echo "gh-missing-repo $*" >>"${PR_LOG}"
	exit 1
fi
read_state() { cat "${PR_STATE}/$1" 2>/dev/null || echo "$2"; }
case "$*" in
"repo view me/repo --json owner,defaultBranchRef") echo '{"owner":{"login":"me"},"defaultBranchRef":{"name":"main"}}' ;;
"pr list --head "*"--state open"*) read_state open '[]' ;;
"pr list --head "*"--state all"*) read_state all '[]' ;;
"pr create"*) echo "https://github.com/me/repo/pull/7" ;;
"pr view "*"--json isDraft"*) echo false ;;
esac
STUB
cat >"${stubs}/wt" <<'STUB'
#!/usr/bin/env bash
echo "wt $*" >>"${PR_LOG}"
[[ "$1 $2" == "list --full" ]] && echo '{"items":[]}'
exit 0
STUB
for tool in kitten terminal-notifier osascript; do
	cat >"${stubs}/${tool}" <<STUB
#!/usr/bin/env bash
echo "${tool} \$*" >>"\${PR_LOG}"
STUB
done
chmod +x "$stubs"/*
export PATH="${stubs}:${PATH}"
unset KITTY_LISTEN_ON KITTY_WINDOW_ID

# The gate, wired the way home/gitconfig wires it (git's hook.*.command), driven
# through the real pre-push path against this tree's scripts: a fresh worktree
# checks the recorded executable bit out without it, so the installed copies
# under ~/.local/share would otherwise win the PATH and the fixture would judge
# those instead of this tree. Only the steps this fixture judges run, so no
# other step's verdict on the fixture's files can decide the result.
mkdir -p "${work}/bin" "${work}/hk-config"
cp "${repo}"/bin/dev-profile-* "${work}/bin/"
chmod +x "${work}/bin/"*
ln -s "${repo}/hk/hk.pkl" "${work}/hk-config/config.pkl"
steps="-S newlines -S private-keys -S trailing-whitespace"
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = DEV_PROFILE_ALLOW_DEFAULT_BRANCH_PUSH=1 PATH="%s:${PATH}" dev-profile-pre-push %s\n' \
	"${work}/bin" "${steps}" >"${work}/gitconfig"
# The default-branch refusal is judged with its own config: no allow override.
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = PATH="%s:${PATH}" dev-profile-pre-push %s\n' \
	"${work}/bin" "${steps}" >"${work}/gitconfig-strict"
export HK_CONFIG_DIR="${work}/hk-config" GIT_CONFIG_GLOBAL="${work}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
unset HK HK_FILE DEV_PROFILE_PUSH_REFS DEV_PROFILE_PUSH_INTRODUCED

publish() { # [args...] — the publish rides the same path `wt pr` uses
	# The copy this fixture chmods: a fresh worktree checks the recorded
	# executable bit out without it, and this script must not depend on it.
	"${work}/bin/dev-profile-pr" "$@" >"${work}/run.txt" 2>&1
}

git init -q --bare "${work}/origin.git"
git clone -q "${work}/origin.git" "${work}/repo" 2>/dev/null
cd "${work}/repo"
# origin is a GitHub URL (git reads it from insteadOf-mapped local storage), so
# the scripts can name the repo; a fork clone's gh would otherwise pick the parent.
git config "url.${work}/origin.git.insteadOf" https://github.com/me/repo.git
git config remote.origin.url https://github.com/me/repo.git
git config user.email t@example.com
git config user.name t
git config commit.gpgsign false # the fixture has no signing key
git switch -q -c main
git commit -q --allow-empty -m base
git push -q origin main
git switch -q -c feature
printf 'published\n' >f.txt
git add -A
git commit -q -m "feat: one file"
reset() { : >"$PR_LOG" && rm -f "$state"/*; }
logged() { grep -qF -- "$1" "$PR_LOG"; }
refused() { grep -q 'refusing the push' "${work}/run.txt"; }

# 1. The first publish of a branch one commit ahead of its base: the gate must
# judge what the push introduces, the remote ref must advance to it, and the PR
# must be created against the base.
reset
publish || fail "a first publish must succeed"
refused && fail "the first publish's push must not be refused"
grep -q 'candidate file' "${work}/run.txt" || fail "the gate must judge the pushed file, not wave the push through"
logged "gh pr create --fill --head feature --base main --repo me/repo" || fail "the first publish must create the PR"
[[ "$(git rev-parse refs/remotes/origin/feature)" == "$(git rev-parse HEAD)" ]] ||
	fail "the remote ref must advance to the published tip"

# 2. The remote is now current, so dev-profile-pr's push updates nothing. With
# an open PR it must print that PR and exit 0, not die at the push: git runs the
# pre-push hook for an up-to-date push and hands it zero ref lines.
reset
cat >"${state}/open" <<EOF
[{"number":7,"url":"https://github.com/me/repo/pull/7","state":"OPEN","isDraft":false,"headRefOid":"$(git rev-parse HEAD)","headRepositoryOwner":{"login":"me"}}]
EOF
publish || fail "a publish over an already-pushed branch with an open PR must succeed"
refused && fail "a push that updates nothing must not be refused"
grep -qF "PR: https://github.com/me/repo/pull/7" "${work}/run.txt" || fail "the open PR must be reused"
logged "pr create" && fail "an open PR must not be recreated"

# 3. The same current remote with no open PR: the publish must reach
# `gh pr create`, which is where `wt pr` died before the gate knew that zero
# refs push nothing.
reset
publish || fail "a publish over an already-pushed branch must succeed"
refused && fail "a push that updates nothing must not be refused"
logged "gh pr create --fill --head feature --base main --repo me/repo" || fail "the publish must reach gh pr create"

# 4. The default-branch refusal still refuses a real push of the default branch.
git switch -q main
git commit -q --allow-empty -m "on main"
if GIT_CONFIG_GLOBAL="${work}/gitconfig-strict" git push origin main >"${work}/run.txt" 2>&1; then
	fail "a push of the default branch must be refused"
fi
grep -q 'refusing to push refs/heads/main' "${work}/run.txt" ||
	fail "the default-branch refusal must name what it refused"

echo "pr-push fixture ok"
