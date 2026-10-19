#!/usr/bin/env bash
# The edges of the push autofix, against real git and hk:
#   fork     a clone pushed to a new remote fixes only its own commits, not the cloned history
#   refs     only the checked-out branch pushed to its own name is fixed
#   optout   DEV_PROFILE_AUTOFIX=0 leaves a raw push's failure alone
#   remotes  dev-profile-push-remote resolves --repo=<name>, a URL and a typo
#   markers  commits made through the hooks are marked, and a marked commit is not fixed again
#   head     a dangling <remote>/HEAD is repaired after a push
# Cases run in parallel; CASES="fork refs" runs only those.
# Usage: autofix-push-edges-fixture.sh <generated-dir>
FIXTURE=autofix-push-edges
# shellcheck source=tests/autofix-push-env.sh
source "$(dirname "$0")/autofix-push-env.sh"

zeros=0000000000000000000000000000000000000000
hooked() { git notes --ref=dev-profile-hooked show "${1:-HEAD}" >/dev/null 2>&1; }

# An upstream repo holding unfixed history, and a clone of it; prints the clone's path.
clone_of_unfixed_upstream() { # <name>
	local seed="${work}/$1-seed"
	git init -q --bare -b main "${work}/$1-up.git"
	git init -q -b main "${seed}"
	git -C "${seed}" remote add origin "${work}/$1-up.git"
	(cd "${seed}" && commit_unfixed && HK=0 git push -q origin main)
	git clone -q "${work}/$1-up.git" "${work}/$1"
	echo "${work}/$1"
}

case_fork() {
	output="${work}/fork.out"
	repo="$(clone_of_unfixed_upstream fork)"
	cd "${repo}"
	printf 'import os\n\nprint(7)\n' >local.py
	git add -A
	HK=0 git commit -q -m "feat: add local"
	git init -q --bare -b main "${work}/fork-remote.git"
	git remote add fork "${work}/fork-remote.git"
	# The push itself may still be refused: the fork has none of the cloned history, so the push
	# checks judge all of it. What matters here is which files the fixers touched.
	dev-profile-push fork main >"${output}" 2>&1 || true
	[[ "$(git log -1 --format=%s)" == "${style}" ]] || fail "fork: no style commit"
	[[ "$(git show --format= --name-only HEAD)" == "local.py" ]] || fail "fork: the style commit touched more than the local commit's files: $(git show --format= --name-only HEAD | paste -sd' ' -)"
	grep -q '^import os' app.py || fail "fork: the cloned history was reformatted"
}

case_refs() {
	output="${work}/refs.out"
	repo="$(new_repo refs)"
	cd "${repo}"
	commit_unfixed
	local sha head_before
	sha="$(git rev-parse HEAD)"
	head_before="${sha}"

	git switch -q -c feat
	printf 'refs/heads/main %s refs/heads/main %s\n' "${sha}" "${zeros}" >"${work}/refs-main"
	SAH_PUSH_REFS="${work}/refs-main" dev-profile-autofix >"${output}" 2>&1 || true
	[[ "$(git rev-parse HEAD)" == "${head_before}" && ! -s "${output}" ]] || fail "refs: pushing main from feat must not fix feat"

	git switch -q main
	printf 'refs/heads/main %s refs/heads/other %s\n' "${sha}" "${zeros}" >"${work}/refs-other"
	SAH_PUSH_REFS="${work}/refs-other" dev-profile-autofix >"${output}" 2>&1 || true
	[[ "$(git rev-parse HEAD)" == "${head_before}" && ! -s "${output}" ]] || fail "refs: pushing main:other must not fix main"
}

case_optout() {
	output="${work}/optout.out"
	repo="$(new_repo optout)"
	cd "${repo}"
	commit_unfixed
	local before code=0
	before="$(git rev-parse HEAD)"
	DEV_PROFILE_AUTOFIX=0 git push origin main >"${output}" 2>&1 || code=$?
	[[ "${code}" -ne 0 ]] || fail "optout: the unfixed push must fail its checks"
	[[ "$(git rev-parse HEAD)" == "${before}" ]] || fail "optout: DEV_PROFILE_AUTOFIX=0 still committed fixes"
	! grep -q '^fixed' "${output}" || fail "optout: DEV_PROFILE_AUTOFIX=0 still printed a fix line"
}

case_remotes() {
	output="${work}/remotes.out"
	repo="$(new_repo remotes)"
	cd "${repo}"
	git init -q --bare -b main "${work}/other.git"
	git remote add other "${work}/other.git"
	check() { # <expected> <git push args...>
		local want="$1" got
		shift
		got="$(dev-profile-push-remote "$@")"
		[[ "${got}" == "${want}" ]] || fail "remotes: dev-profile-push-remote $* printed '${got}', wanted '${want}'"
	}
	check origin
	check origin origin main
	check other other main
	check other --repo=other
	check other --repo other
	check other -o ci.skip other main
	check origin "${repo}.git" main
	check other "${work}/other.git"
	check "" "${work}/nowhere.git"
	check "" orgin main
}

case_markers() {
	output="${work}/markers.out"
	repo="$(new_repo markers)"
	cd "${repo}"
	git switch -q -c work # the hooks refuse a commit on main
	printf 'print("hi")\n' >a.py
	git add -A
	git commit -q -m "feat: add a" >"${output}" 2>&1 || fail "markers: the hooked commit failed"
	hooked || fail "markers: a commit made through the hooks has no note"
	printf 'print("b")\n' >b.py
	git add -A
	HK=0 git commit -q -m "feat: add b"
	! hooked || fail "markers: a commit made with HK=0 has a note"
	printf 'print("c")\n' >c.py
	git add -A
	git commit -q --no-verify -m "feat: add c"
	! hooked || fail "markers: a commit made past the hooks has a note"

	repo="$(new_repo marked)"
	cd "${repo}"
	commit_unfixed
	git notes --ref=dev-profile-hooked add -m hooked HEAD
	local before
	before="$(git rev-parse HEAD)"
	dev-profile-autofix >"${output}" 2>&1 || true
	[[ "$(git rev-parse HEAD)" == "${before}" && ! -s "${output}" ]] || fail "markers: a hooked commit was fixed again"
}

case_head() {
	output="${work}/head.out"
	repo="$(clone_of_unfixed_upstream head)"
	cd "${repo}"
	git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/gone
	! git rev-parse -q --verify refs/remotes/origin/HEAD >/dev/null 2>&1 || fail "head: the fixture's dangling HEAD resolves"
	printf 'print("hi")\n' >clean.py
	git add -A
	HK=0 git commit -q -m "feat: add clean"
	git notes --ref=dev-profile-hooked add -m hooked HEAD
	dev-profile-push origin main >"${output}" 2>&1 || fail "head: the push failed"
	git rev-parse -q --verify refs/remotes/origin/HEAD >/dev/null 2>&1 || fail "head: the dangling origin/HEAD was not repaired"
}

read -r -a cases <<<"${CASES:-fork refs optout remotes markers head}"
run_cases "${cases[@]}"
echo "autofix-push-edges fixture ok"
