#!/usr/bin/env bash
# A push fixes what the tools can fix, against real git, real hk and a local bare remote.
#   first        dev-profile-push to an EMPTY remote: one style commit is pushed, no git fatal,
#                and <remote>/HEAD exists afterwards
#   dirty        files with staged or unstaged edits are left alone and named
#   clean        a clean push adds no commit and prints no fix line
#   raw          a raw `git push`: the pre-push hook commits the fixes, stops with one line, and the
#                same push passes
#   signed       the fix commit is signed when the user's config signs
# Cases run in parallel; CASES="first raw" runs only those.
# Usage: autofix-push-fixture.sh <generated-dir>
FIXTURE=autofix-push
# shellcheck source=tests/autofix-push-env.sh
source "$(dirname "$0")/autofix-push-env.sh"

case_first() {
	output="${work}/first.out"
	repo="$(new_repo first)"
	cd "${repo}"
	commit_unfixed
	local code=0
	dev-profile-push origin main >"${output}" 2>&1 || code=$?
	[[ "${code}" -eq 0 ]] || fail "first push: dev-profile-push must exit 0, got ${code}"
	no_git_noise "first push"
	grep -Eq "^fixed 3 files → [0-9a-f]+ ${style}\$" "${output}" || fail "first push: no 'fixed 3 files' line"
	[[ "$(remote_git log -1 --format=%s main)" == "${style}" ]] || fail "first push: the remote tip is not the style commit"
	[[ "$(remote_git rev-list --count main)" -eq 2 ]] || fail "first push: expected the feature commit plus one style commit"
	! remote_git show main:app.py | grep -q '^import os' || fail "first push: the unused import is still on the remote"
	remote_git ls-tree main run.sh | grep -q '^100755 ' || fail "first push: run.sh is not executable on the remote"
	git symbolic-ref -q refs/remotes/origin/HEAD >/dev/null || fail "first push: refs/remotes/origin/HEAD was not set"
}

case_dirty() {
	output="${work}/dirty.out"
	repo="$(new_repo dirty)"
	cd "${repo}"
	commit_unfixed
	printf 'import os\nimport sys\n\nprint(sys.argv)  # edited\n' >app.py
	printf 'import os\n\nprint(3)\n' >util.py
	git add util.py
	cp app.py "${work}/app.expected"
	cp util.py "${work}/util.expected"
	git diff --cached >"${work}/staged.expected"
	dev-profile-push origin HEAD:refs/heads/main >"${output}" 2>&1 || true
	grep -Eq '^left alone \(uncommitted edits\): app\.py util\.py$' "${output}" || fail "uncommitted: the output does not name the files left alone"
	cmp -s app.py "${work}/app.expected" || fail "uncommitted: app.py changed"
	cmp -s util.py "${work}/util.expected" || fail "uncommitted: util.py changed"
	git diff --cached >"${work}/staged.actual"
	cmp -s "${work}/staged.actual" "${work}/staged.expected" || fail "uncommitted: the staged edit changed"
	[[ "$(git log -1 --format=%s)" == "${style}" ]] || fail "uncommitted: the file with no edits was not fixed and committed"
	[[ "$(git show --format= --name-only HEAD)" == "run.sh" ]] || fail "uncommitted: the style commit holds more than run.sh"
}

case_clean() {
	output="${work}/clean.out"
	repo="$(new_repo clean)"
	cd "${repo}"
	printf 'print("hi")\n' >main.py
	git add -A
	HK=0 git commit -q -m "feat: add main"
	local code=0
	dev-profile-push origin main >"${output}" 2>&1 || code=$?
	[[ "${code}" -eq 0 ]] || fail "clean push: must exit 0, got ${code}"
	! grep -Eq '^(fixed|left alone)' "${output}" || fail "clean push: printed a fix line"
	[[ "$(remote_git rev-list --count main)" -eq 1 ]] || fail "clean push: a commit was added"
	[[ "$(git rev-list --count HEAD)" -eq 1 ]] || fail "clean push: a local commit was added"
}

case_raw() {
	output="${work}/raw.out"
	repo="$(new_repo raw)"
	cd "${repo}"
	commit_unfixed
	local code=0
	git push origin main >"${output}" 2>&1 || code=$?
	[[ "${code}" -ne 0 ]] || fail "raw push: the first push must stop after committing fixes"
	no_git_noise "raw push"
	grep -Eq '^fixed 3 files → [0-9a-f]+; run the same push again$' "${output}" || fail "raw push: no 'run the same push again' line"
	[[ "$(git log -1 --format=%s)" == "${style}" ]] || fail "raw push: the fixes were not committed"
	! remote_git rev-parse -q --verify refs/heads/main >/dev/null || fail "raw push: something was pushed before the fixes"
	code=0
	git push origin main >"${output}" 2>&1 || code=$?
	[[ "${code}" -eq 0 ]] || fail "raw push: the same push again must pass, got ${code}"
	[[ "$(remote_git rev-parse main)" == "$(git rev-parse HEAD)" ]] || fail "raw push: the remote is not at the fixed commit"
}

# Commits are signed with an SSH key when the repo's config says so; the fix commit is made in a
# scratch checkout of the same repo, so it must be signed too.
case_signed() {
	output="${work}/signed.out"
	repo="$(new_repo signed)"
	cd "${repo}"
	ssh-keygen -q -t ed25519 -N '' -C fixture -f "${work}/signing-key"
	echo "fixture@example.com $(cat "${work}/signing-key.pub")" >"${work}/allowed-signers"
	git config --local gpg.format ssh
	git config --local user.signingkey "${work}/signing-key.pub"
	git config --local gpg.ssh.allowedSignersFile "${work}/allowed-signers"
	git config --local commit.gpgsign true
	printf '#!/usr/bin/env bash\necho hi\n' >run.sh
	chmod 644 run.sh
	git add -A
	HK=0 git commit -q -m "feat: add script"
	[[ "$(git log -1 --format=%G?)" == G ]] || fail "signed: the base commit is not signed; the fixture setup is wrong"
	dev-profile-push origin main >"${output}" 2>&1 || fail "signed: dev-profile-push failed"
	[[ "$(git log -1 --format=%s)" == "${style}" ]] || fail "signed: no fix commit"
	[[ "$(git log -1 --format=%G?)" == G ]] || fail "signed: the fix commit is not signed (%G? is $(git log -1 --format=%G?))"
}

read -r -a cases <<<"${CASES:-first dirty clean raw signed}"
run_cases "${cases[@]}"
echo "autofix-push fixture ok"
