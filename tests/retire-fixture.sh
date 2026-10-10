#!/usr/bin/env bash
# `wt retire` backs a clone up, proves GitHub holds everything in it, and only
# then moves it and its worktrees to the Trash; otherwise it deletes nothing.
# Real git and a real bare origin; `trash` is a stub that moves into a bin.
# Usage: retire-fixture.sh <generated-dir>
set -euo pipefail
export HK=0 # no global git hooks inside the fixture repos

out="${1:?usage: retire-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
retire="${out}/bin/dev-profile-retire"

fail() {
	echo "FAIL retire fixture: $*" >&2
	exit 1
}

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false

stubs="${work}/stubs"
mkdir -p "${stubs}" "${work}/bin"
cat >"${stubs}/trash" <<'TRASH'
#!/usr/bin/env bash
mv "$1" "${TRASH_BIN}/$(basename "$1")-$$-${RANDOM}"
TRASH
chmod +x "${stubs}/trash"
export PATH="${stubs}:${PATH}" TRASH_BIN="${work}/bin"

commit() { # <repo> <file> <content>
	printf '%s\n' "$3" >"$1/$2"
	git -C "$1" add "$2"
	git -C "$1" commit -q -m "$2: $3"
}
on_origin() { git -C "${work}/origin.git" rev-parse --verify --quiet "refs/heads/$1"; }
clone() { # <name>: a fresh clone of origin
	git clone -q "${work}/origin.git" "${work}/$1" 2>/dev/null
	git -C "${work}/$1" remote set-head origin main
}

git init -q --bare --initial-branch=main "${work}/origin.git"
git clone -q "${work}/origin.git" "${work}/seed" 2>/dev/null
git -C "${work}/seed" switch -q -c main
commit "${work}/seed" base.txt base
git -C "${work}/seed" switch -q -c shared main
commit "${work}/seed" shared.txt base
git -C "${work}/seed" push -q origin main shared

# A clone with every kind of unique state retires: all of it reaches GitHub,
# then the clone and its worktree go to the Trash.
clone e
git -C "${work}/e" switch -q -c feat/e main
commit "${work}/e" e.txt e
git -C "${work}/e" switch -q main
echo stashed >"${work}/e/stash.txt"
git -C "${work}/e" stash push -q -u
git -C "${work}/e" worktree add -q "${work}/e-wip" -b feat/wip main
echo unfinished >"${work}/e-wip/wip.txt"
(cd "${work}/e" && "${retire}") >"${work}/e.out" 2>&1 || fail "a clone with everything backed up must retire: $(cat "${work}/e.out")"
[[ ! -e "${work}/e" && ! -e "${work}/e-wip" ]] || fail "a retired clone and its worktrees must be gone"
[[ "$(find "${work}/bin" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')" -eq 2 ]] || fail "the clone and its worktree must be in the Trash"
on_origin feat/e >/dev/null || fail "an unpushed branch must reach GitHub before the clone goes"
git -C "${work}/origin.git" for-each-ref --format='%(refname)' refs/heads/backup | grep -q '/wip/feat/wip$' ||
	fail "uncommitted changes must reach GitHub before the clone goes"
git -C "${work}/origin.git" for-each-ref --format='%(refname)' refs/heads/backup | grep -q '/stash-' ||
	fail "a stash must reach GitHub before the clone goes"

# --dry-run deletes nothing and pushes nothing.
clone f
git -C "${work}/f" switch -q -c feat/f main && commit "${work}/f" f.txt f
(cd "${work}/f" && "${retire}" --dry-run) >"${work}/f.out" 2>&1 || fail "retire --dry-run must succeed: $(cat "${work}/f.out")"
[[ -d "${work}/f" ]] || fail "retire --dry-run must not delete"
on_origin feat/f >/dev/null && fail "retire --dry-run must not push"
grep -q 'Dry run: GitHub holds everything' "${work}/f.out" && fail "a dry run must not vouch for work it has not pushed"

# Conflicts only: each is backed up, so the clone may still retire.
clone g
git -C "${work}/seed" switch -q shared && commit "${work}/seed" shared.txt github && git -C "${work}/seed" push -q origin shared
git -C "${work}/g" switch -q -c shared origin/shared # the version before GitHub moved on
commit "${work}/g" shared.txt local
git -C "${work}/g" switch -q main
(cd "${work}/g" && "${retire}") >"${work}/g.out" 2>&1 || fail "a clone whose only gaps are backed-up conflicts must retire: $(cat "${work}/g.out")"
[[ ! -e "${work}/g" ]] || fail "a clone with backed-up conflicts must be retired"
git -C "${work}/origin.git" for-each-ref --format='%(refname)' refs/heads/backup | grep -q '/shared$' ||
	fail "the conflicting branch must be backed up before the clone goes"

# The check stands on its own: with a backup step that backs up nothing, an
# unpushed branch keeps the clone.
clone j
git -C "${work}/j" switch -q -c feat/j main && commit "${work}/j" j.txt j
code=0
(cd "${work}/j" && DEV_PROFILE_RETIRE_SYNC=true "${retire}") >"${work}/j.out" 2>&1 || code=$?
[[ "${code}" -ne 0 && -d "${work}/j" ]] || fail "work missing from GitHub must keep the clone, whatever the backup step said"
grep -q "missing  *branch feat/j" "${work}/j.out" || fail "retire must name what is missing"

# A file too big to back up keeps the clone.
clone h
head -c 2097152 /dev/zero >"${work}/h/big.bin"
code=0
(cd "${work}/h" && DEV_PROFILE_SYNC_MAX_FILE_MB=1 "${retire}") >"${work}/h.out" 2>&1 || code=$?
[[ "${code}" -ne 0 ]] || fail "a file too big to back up must stop retire"
[[ -d "${work}/h" ]] || fail "a clone with a file too big to back up must be kept"

# An ignored directory holding its own repository keeps the clone.
clone i
echo vendor/ >"${work}/i/.git/info/exclude"
git init -q "${work}/i/vendor"
code=0
(cd "${work}/i" && "${retire}") >"${work}/i.out" 2>&1 || code=$?
[[ "${code}" -ne 0 ]] || fail "a nested repository must stop retire"
[[ -d "${work}/i" ]] || fail "a clone holding a nested repository must be kept"
grep -q 'separate repository' "${work}/i.out" || fail "retire must say a nested repository stopped it"

# A nested clone whose own GitHub holds everything does not stop retire.
clone k
echo vendor/ >"${work}/k/.git/info/exclude"
git clone -q "${work}/origin.git" "${work}/k/vendor" 2>/dev/null
(cd "${work}/k" && "${retire}") >"${work}/k.out" 2>&1 || fail "a nested clone with nothing unique must not stop retire: $(cat "${work}/k.out")"
[[ ! -e "${work}/k" ]] || fail "a clone whose nested repository is all on GitHub must be retired"

# A nested clone with a commit its GitHub lacks does stop it.
clone l
echo vendor/ >"${work}/l/.git/info/exclude"
git clone -q "${work}/origin.git" "${work}/l/vendor" 2>/dev/null
commit "${work}/l/vendor" only-here.txt x
code=0
(cd "${work}/l" && "${retire}") >"${work}/l.out" 2>&1 || code=$?
[[ "${code}" -ne 0 && -d "${work}/l" ]] || fail "a nested repository with unpushed work must stop retire"
grep -q "work its own GitHub lacks" "${work}/l.out" || fail "retire must say why a nested repository stopped it"
[[ "$(grep -c "separate repository" "${work}/l.out")" -eq 1 ]] || fail "a nested repository must be listed once"
echo "retire fixture ok"
