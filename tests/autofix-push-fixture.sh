#!/usr/bin/env bash
# A push fixes what the tools can fix, against real git, real hk and a local bare remote.
# History is committed with the hooks off (HK=0), so its content reaches push unfixed.
#   first push        dev-profile-push to an EMPTY remote: one style commit is pushed, no git fatal,
#                     and <remote>/HEAD exists afterwards
#   uncommitted work  files with staged or unstaged edits are left alone and named
#   nothing to fix    a clean push adds no commit and prints no fix line
#   raw git push      the pre-push hook commits the fixes, stops with one line, and the same push passes
# Usage: autofix-push-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: autofix-push-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
output="${work}/output.txt"
style="style: apply profile fixes"

fail() {
	echo "FAIL autofix-push fixture: $*" >&2
	[[ ! -f "${output}" ]] || sed 's/^/  | /' "${output}" >&2
	exit 1
}

# The generated hk config, active the way bootstrap links it; the hooks the way
# install-git-hooks writes them, with the pre-push command this profile installs.
mkdir -p "${work}/hk-config"
ln -s "${out}/hk-config.pkl" "${work}/hk-config/config.pkl"
unset HK_FILE
export HK_CONFIG_DIR="${work}/hk-config"
export PATH="${out}/bin:${PATH}"
export GIT_CONFIG_GLOBAL="${work}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
git config --global user.name fixture
git config --global user.email fixture@example.com
git config --global commit.gpgsign false
install_hook() { # <event> <command>
	git config --global "hook.fixture-$1.event" "$1"
	git config --global "hook.fixture-$1.command" "test \"\${HK:-1}\" = \"0\" || $2"
}
install_hook pre-commit "hk run pre-commit --staged"
install_hook commit-msg "hk run commit-msg"
install_hook pre-push "${out}/bin/dev-profile-pre-push"

# A repo whose "origin" is an empty bare repo; prints the repo path.
new_repo() { # <name>
	local dir="${work}/$1"
	git init -q --bare -b main "${dir}.git"
	git init -q -b main "${dir}"
	git -C "${dir}" remote add origin "${dir}.git"
	echo "${dir}"
}

# Unused imports (ruff F401) and a shebang script without its executable bit,
# committed with the hooks off.
commit_unfixed() {
	printf 'import os\nimport sys\n\nprint(sys.argv)\n' >app.py
	printf 'import os\n\nprint(2)\n' >util.py
	printf '#!/usr/bin/env bash\necho hi\n' >run.sh
	chmod 644 run.sh
	git add -A
	HK=0 git commit -q -m "feat: add app"
}

remote_git() { git --git-dir="${repo}.git" "$@"; }
no_git_fatal() { ! grep -Eq '(fatal|warning):' "${output}" || fail "$1: git printed a fatal or a warning"; }

# ---- 1. First push to an empty remote.
repo="$(new_repo first)"
cd "${repo}"
commit_unfixed
code=0
dev-profile-push origin main >"${output}" 2>&1 || code=$?
[[ "${code}" -eq 0 ]] || fail "first push: dev-profile-push must exit 0, got ${code}"
no_git_fatal "first push"
grep -Eq "^fixed 3 files → [0-9a-f]+ ${style}\$" "${output}" || fail "first push: no 'fixed 3 files' line"
[[ "$(remote_git log -1 --format=%s main)" == "${style}" ]] || fail "first push: the remote tip is not the style commit"
[[ "$(remote_git rev-list --count main)" -eq 2 ]] || fail "first push: expected the feature commit plus one style commit"
! remote_git show main:app.py | grep -q '^import os' || fail "first push: the unused import is still on the remote"
remote_git ls-tree main run.sh | grep -q '^100755 ' || fail "first push: run.sh is not executable on the remote"
git symbolic-ref -q refs/remotes/origin/HEAD >/dev/null || fail "first push: refs/remotes/origin/HEAD was not set"

# ---- 2. Uncommitted work is never touched.
repo="$(new_repo dirty)"
cd "${repo}"
commit_unfixed
printf 'import os\nimport sys\n\nprint(sys.argv)  # edited\n' >app.py
printf 'import os\n\nprint(3)\n' >util.py
git add util.py
cp app.py "${work}/app.expected"
cp util.py "${work}/util.expected"
git diff --cached >"${work}/staged.expected"
dev-profile-push origin main >"${output}" 2>&1 || true
grep -Eq '^left alone \(uncommitted edits\): app\.py util\.py$' "${output}" || fail "uncommitted: the output does not name the files left alone"
cmp -s app.py "${work}/app.expected" || fail "uncommitted: app.py changed"
cmp -s util.py "${work}/util.expected" || fail "uncommitted: util.py changed"
git diff --cached >"${work}/staged.actual"
cmp -s "${work}/staged.actual" "${work}/staged.expected" || fail "uncommitted: the staged edit changed"
[[ "$(git log -1 --format=%s)" == "${style}" ]] || fail "uncommitted: the file with no edits was not fixed and committed"
[[ "$(git show --format= --name-only HEAD)" == "run.sh" ]] || fail "uncommitted: the style commit holds more than run.sh"

# ---- 3. Nothing to fix.
repo="$(new_repo clean)"
cd "${repo}"
printf 'print("hi")\n' >main.py
git add -A
HK=0 git commit -q -m "feat: add main"
code=0
dev-profile-push origin main >"${output}" 2>&1 || code=$?
[[ "${code}" -eq 0 ]] || fail "clean push: must exit 0, got ${code}"
! grep -Eq '^(fixed|left alone)' "${output}" || fail "clean push: printed a fix line"
[[ "$(remote_git rev-list --count main)" -eq 1 ]] || fail "clean push: a commit was added"
[[ "$(git rev-list --count HEAD)" -eq 1 ]] || fail "clean push: a local commit was added"

# ---- 4. A raw `git push`: the pre-push hook commits the fixes and stops; the same push passes.
repo="$(new_repo raw)"
cd "${repo}"
commit_unfixed
code=0
git push origin main >"${output}" 2>&1 || code=$?
[[ "${code}" -ne 0 ]] || fail "raw push: the first push must stop after committing fixes"
no_git_fatal "raw push"
grep -Eq '^fixed 3 files → [0-9a-f]+; run the same push again$' "${output}" || fail "raw push: no 'run the same push again' line"
[[ "$(git log -1 --format=%s)" == "${style}" ]] || fail "raw push: the fixes were not committed"
! remote_git rev-parse -q --verify refs/heads/main >/dev/null || fail "raw push: something was pushed before the fixes"
code=0
git push origin main >"${output}" 2>&1 || code=$?
[[ "${code}" -eq 0 ]] || fail "raw push: the same push again must pass, got ${code}"
[[ "$(remote_git rev-parse main)" == "$(git rev-parse HEAD)" ]] || fail "raw push: the remote is not at the fixed commit"

echo "autofix-push fixture ok"
