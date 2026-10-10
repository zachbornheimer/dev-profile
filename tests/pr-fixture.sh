#!/usr/bin/env bash
# The PR scripts behind `wt pr`, `wt pr-draft`, `wt pr-auto`, `wt ship` and
# `wt prune`: what they publish, skip, merge, notify and remove. Real git;
# gh, wt, kitten and the notifiers are stubs that log their arguments.
# Usage: pr-fixture.sh <generated-dir>
set -euo pipefail
export HK=0 # no global git hooks inside the fixture repo

out="${1:?usage: pr-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL pr fixture: $*" >&2
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
read_state() { cat "${PR_STATE}/$1" 2>/dev/null || echo "$2"; }
case "$*" in
"repo view --json owner,defaultBranchRef") echo '{"owner":{"login":"me"},"defaultBranchRef":{"name":"main"}}' ;;
"repo view --json viewerDefaultMergeMethod"*) echo squash ;;
"pr list --head "*"--state open"*) read_state open '[]' ;;
"pr list --head "*"--state all"*) read_state all '[]' ;;
"pr list --state merged"*) read_state merged '' ;;
"pr create"*) echo "https://github.com/me/repo/pull/7" ;;
"pr view "*"--json isDraft"*) echo false ;;
"pr view "*"--json number,title,url,headRefName"*) echo "{\"number\":7,\"title\":\"t\",\"url\":\"https://github.com/me/repo/pull/7\",\"headRefName\":\"feature\",\"isCrossRepository\":$(read_state fork false)}" ;;
"pr view "*"--json state"*)
	# A one-shot network failure, as a blip mid-poll.
	if [[ -e "${PR_STATE}/blip" ]]; then
		rm "${PR_STATE}/blip"
		exit 1
	fi
	read_state pr_state OPEN
	;;
"pr merge"*)
	echo MERGED >"${PR_STATE}/pr_state"
	if [[ -e "${PR_STATE}/blip_after_merge" ]]; then touch "${PR_STATE}/blip"; fi
	;;
"pr view "*"--json headRefOid"*) read_state oid '' ;;
"pr checks "*"--json name"*)
	# checks_seq: one count per call, the last repeating, as CI registers.
	if [[ -s "${PR_STATE}/checks_seq" ]]; then
		head -n 1 "${PR_STATE}/checks_seq"
		if [[ "$(wc -l <"${PR_STATE}/checks_seq")" -gt 1 ]]; then
			tail -n +2 "${PR_STATE}/checks_seq" >"${PR_STATE}/checks_seq.next"
			mv "${PR_STATE}/checks_seq.next" "${PR_STATE}/checks_seq"
		fi
	else
		read_state checks 1
	fi
	;;
"pr checks "*"--watch"*) exit "$(read_state checks_exit 0)" ;;
esac
STUB
cat >"${stubs}/wt" <<'STUB'
#!/usr/bin/env bash
echo "wt $*" >>"${PR_LOG}"
[[ "$1 $2" == "list --full" ]] && echo '{"items":[]}'
[[ "$1 $2" == "step commit" ]] && git add -A && git commit -qm stub
exit 0
STUB
for tool in kitten terminal-notifier osascript; do
	cat >"${stubs}/${tool}" <<STUB
#!/usr/bin/env bash
echo "${tool} \$*" >>"\${PR_LOG}"
STUB
done
chmod +x "$stubs"/*

git init -q --bare "${work}/origin.git"
git clone -q "${work}/origin.git" "${work}/repo" 2>/dev/null
cd "${work}/repo"
git config user.email t@example.com
git config user.name t
git switch -q -c main
git commit -q --allow-empty -m base
git push -q origin main
git switch -q -c feature

export PATH="${stubs}:${PATH}"
unset KITTY_LISTEN_ON KITTY_WINDOW_ID
publish="${out}/bin/dev-profile-pr"
watch="${out}/bin/dev-profile-pr-watch"
prune="${out}/bin/dev-profile-prune"

reset() { : >"$PR_LOG" && rm -f "$state"/*; }
logged() { grep -qF -- "$1" "$PR_LOG"; }

reset
"$publish" >/dev/null 2>&1 || fail "branch equal to base must exit 0"
logged "pr create" && fail "branch equal to base must not create a PR"

git commit -q --allow-empty -m change
reset
"$publish" >/dev/null 2>&1 || fail "branch ahead of base must publish"
logged "gh pr create --fill --head feature --base main" || fail "must create a PR against main"
logged "--draft" && fail "plain pr must not be a draft"

reset
"$publish" --draft >/dev/null 2>&1 || fail "pr --draft must publish"
logged "--base main --draft" || fail "pr --draft must create a draft"

reset
code=0
"$publish" --draft --auto >/dev/null 2>&1 || code=$?
[[ "$code" -eq 2 ]] || fail "--draft --auto must be rejected with exit 2, got ${code}"

reset
echo "[{\"number\":3,\"state\":\"MERGED\",\"headRefOid\":\"$(git rev-parse HEAD)\"}]" >"${state}/all"
"$publish" >/dev/null 2>&1 || fail "previously merged branch must exit 0"
logged "pr create" && fail "a merged PR with no new commits must not be recreated"

reset
DEV_PROFILE_PR_WATCH=tab KITTY_LISTEN_ON=unix:/tmp/fixture KITTY_WINDOW_ID=9 "$publish" --auto >/dev/null 2>&1 || fail "pr --auto must publish"
logged "kitten @ --to unix:/tmp/fixture launch --type=tab --keep-focus" || fail "pr --auto must open a kitty watcher tab"
logged "--match id:9 ${watch} https://github.com/me/repo/pull/7" || fail "the kitty tab must run the watcher on the PR"

# `wt pr --create=… -- CMD` runs CMD on a fresh branch, then publishes it.
git switch -q -c chore/edit main
reset
"$publish" -- sh -c 'echo x >f' >/dev/null 2>&1 || fail "pr -- CMD must publish the command's change"
logged "wt step commit" || fail "pr -- CMD must commit the change"
logged "gh pr create --fill --head chore/edit" || fail "pr -- CMD must create a PR"

git switch -q -c chore/noop main
reset
"$publish" -- true >/dev/null 2>&1 || fail "a command that changes nothing must exit 0"
logged "wt remove --foreground chore/noop" || fail "a command that changes nothing must remove its worktree"
logged "pr create" && fail "a command that changes nothing must not create a PR"

reset
"$publish" -- false >/dev/null 2>&1 && fail "a failed command must exit nonzero"
logged "pr create" && fail "a failed command must not create a PR"
git switch -q feature

export DEV_PROFILE_PR_POLL=0 DEV_PROFILE_PR_CHECKS_WAIT=0
git push -q origin feature
reset
echo 1 >"${state}/checks_exit"
"$watch" 7 >/dev/null 2>&1 </dev/null && fail "failed CI must exit nonzero"
logged "terminal-notifier -title PR #7: CI failed" || fail "failed CI must notify"
logged "pr merge" && fail "failed CI must not merge"

reset
git rev-parse feature >"${state}/oid"
"$watch" 7 >/dev/null 2>&1 </dev/null || fail "green CI must merge and clean up"
logged "gh pr merge 7 --auto --squash" || fail "green CI must arm the merge with the repo's method"
logged "terminal-notifier -title PR #7 merged" || fail "a merge must notify"
logged "wt remove --foreground --force-delete feature" || fail "a merged tip must be force-removed"
gone() { ! git ls-remote --exit-code --heads origin "$1" >/dev/null 2>&1; }
gone feature || fail "a merge must delete the remote branch that holds the merged tip"

# Commits pushed after the merge keep the remote branch.
git push -q origin feature
reset
git rev-parse main >"${state}/oid"
echo MERGED >"${state}/pr_state"
"$watch" 7 >/dev/null 2>&1 </dev/null || true
gone feature && fail "a remote branch that moved past the merged commit must be kept"

# A failed GitHub poll is not a closed PR.
reset
touch "${state}/blip_after_merge"
"$watch" 7 >/dev/null 2>&1 </dev/null || fail "a network blip while polling must not fail the watch"
logged "closed without merging" && fail "a network blip must not read as closed"

# CI registers checks one by one; watch only once the count holds.
reset
printf '1\n1\n2\n2\n' >"${state}/checks_seq"
"$watch" 7 >/dev/null 2>&1 </dev/null || fail "late-registering checks must still merge"
[[ "$(grep -c -- '--json name' "$PR_LOG")" -ge 4 ]] || fail "the watch must wait for the check count to settle"

# A fork's branch is not ours to delete.
reset
echo true >"${state}/fork"
echo MERGED >"${state}/pr_state"
"$watch" 7 >/dev/null 2>&1 </dev/null || fail "a merged fork PR must exit 0"
logged "wt remove" && fail "a merged fork PR must not remove a local branch"

reset
echo MERGED >"${state}/pr_state"
"$watch" 7 >/dev/null 2>&1 </dev/null || fail "an already merged PR must clean up"
logged "pr merge" && fail "an already merged PR must not be merged again"
logged "wt remove --foreground feature" || fail "an already merged PR must remove its branch"

reset
printf 'feature %s\nother %s\n' "$(git rev-parse feature)" "$(git rev-parse main)" >"${state}/merged"
"$prune" >/dev/null 2>&1 || fail "prune must succeed"
logged "wt step prune --foreground" || fail "prune must run wt step prune first"
logged "wt remove --foreground --force-delete feature" || fail "prune must remove a branch whose tip GitHub merged"

reset
printf 'feature 0000000000000000000000000000000000000000\n' >"${state}/merged"
"$prune" --dry-run >/dev/null 2>&1 || fail "prune --dry-run must succeed"
logged "wt remove" && fail "prune must not remove a branch whose tip differs from the merged PR"
# Not interactive (a loop, a script): --auto detaches the watcher, no tab.
git switch -q chore/edit
reset
KITTY_LISTEN_ON=unix:/tmp/fixture "$publish" --auto >/dev/null 2>&1 </dev/null || fail "non-interactive pr --auto must publish"
logged "kitten @" && fail "non-interactive pr --auto must not open a kitty tab"
log="$(git rev-parse --path-format=absolute --git-common-dir)/wt/logs/pr-watch-chore-edit.log"
for ((attempt = 0; attempt < 50; attempt++)); do
	grep -q "merged and cleaned up" "$log" 2>/dev/null && break
	sleep 0.2
done
grep -q "merged and cleaned up" "$log" || fail "the detached watcher must run to completion"

echo "pr fixture ok"
