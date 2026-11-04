#!/usr/bin/env bash
# The gate must be stoppable. dev-profile-pre-push used to ignore HUP/INT/TERM,
# so a gate a supervisor's deadline stopped kept running: it could neither be
# interrupted nor finish, and it held the working tree in hk's stash until it
# did. An ignored disposition is inherited across exec, so a stub `hk` that
# signals itself proves it -- if the wrapper still ignored TERM, the stub would
# survive its own signal and say so.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL pre-push-interruptible: $*" >&2
	if [[ -e "${scratch}/out.txt" ]]; then sed 's/^/  | /' "${scratch}/out.txt" >&2; fi
	exit 1
}

mkdir -p "${scratch}/bin"
# The stub the wrapper runs as `hk run pre-push`: it signals itself, so it lives
# to print the marker only if the wrapper handed it an ignored TERM.
cat >"${scratch}/bin/hk" <<'HK'
#!/usr/bin/env bash
kill -TERM "$$" 2>/dev/null || true
echo "STILL_ALIVE_AFTER_TERM" >&2
exit 0
HK
chmod +x "${scratch}/bin/hk"

: >"${scratch}/gitconfig"
export GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE HK_CONFIG_DIR

work="${scratch}/work"
git init -q -b main "${work}"
printf 'base\n' >"${work}/base.txt"
git -C "${work}" add -A
git -C "${work}" -c commit.gpgsign=false commit -qm "chore: base"
git -C "${work}" update-ref refs/remotes/origin/main HEAD
git -C "${work}" switch -q -c feature
printf 'more\n' >>"${work}/base.txt"
git -C "${work}" add -A
git -C "${work}" -c commit.gpgsign=false commit -qm "feat: more"

tip="$(git -C "${work}" rev-parse feature)"
base="$(git -C "${work}" rev-parse main)"
line="refs/heads/feature ${tip} refs/heads/feature ${base}"

rc=0
(cd "${work}" && printf '%s\n' "${line}" |
	PATH="${scratch}/bin:${repo}/bin:${PATH}" dev-profile-pre-push) >"${scratch}/out.txt" 2>&1 || rc=$?

grep -q 'STILL_ALIVE_AFTER_TERM' "${scratch}/out.txt" &&
	fail "the wrapper handed hk an ignored TERM, so the gate cannot be stopped"
grep -q 'was stopped by TERM' "${scratch}/out.txt" ||
	fail "the wrapper must still name the signal that stopped the gate"

echo "ok pre-push-interruptible"
