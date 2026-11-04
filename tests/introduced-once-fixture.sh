#!/usr/bin/env bash
# The files a push introduces are computed once for the push, not once per
# per-file step: dev-profile-pre-push derives them with dev-profile-push-files
# and exports the result as DEV_PROFILE_PUSH_FILES, and every routed step's
# dev-profile-changed-files reads that file. A gate that hands the set down
# re-derives nothing per step; without it (a direct `hk run pre-push`, an older
# wrapper) each call derives the set itself.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL introduced-once: $*" >&2
	[[ ! -f "${scratch}/push.txt" ]] || sed 's/^/  | /' "${scratch}/push.txt" >&2
	exit 1
}

# Tool-free per-file steps route through dev-profile-changed-files, so the gate
# runs real routed calls without another tool deciding the fixture.
steps="-S case-conflicts -S check-added-large-files -S check-executables-have-shebangs -S check-symlinks"

# The profile's hk config, run the way bootstrap links it, plus a
# dev-profile-push-files that counts every derivation the gate asks for.
mkdir -p "${scratch}/hk-config" "${scratch}/fakebin"
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"
cat >"${scratch}/fakebin/dev-profile-push-files" <<STUB
#!/usr/bin/env bash
printf 'derive\n' >>"\${DEV_PROFILE_PUSH_FILES_CALLS}"
exec "${repo}/bin/dev-profile-push-files" "\$@"
STUB
chmod +x "${scratch}/fakebin/dev-profile-push-files"
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = PATH="%s:%s/bin:${PATH}" dev-profile-pre-push %s\n' \
	"${scratch}/fakebin" "${repo}" "${steps}" >"${scratch}/gitconfig"
export HK_CONFIG_DIR="${scratch}/hk-config" GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
export DEV_PROFILE_PUSH_FILES_CALLS="${scratch}/derivations"
unset HK HK_FILE
: >"${scratch}/derivations"

push() { # <cwd> <git args...>
	local cwd="$1"
	shift
	(cd "${cwd}" && git "$@") >"${scratch}/push.txt" 2>&1
}

git init -q --bare "${scratch}/remote.git"
git init -q -b main "${scratch}/work"
git -C "${scratch}/work" remote add origin "${scratch}/remote.git"
printf 'base\n' >"${scratch}/work/base.txt"
git -C "${scratch}/work" add -A
git -C "${scratch}/work" -c commit.gpgsign=false commit -qm "base"
# The default branch is published without pushing it: the wrapper refuses a push
# of refs/heads/main.
git -C "${scratch}/work" update-ref refs/remotes/origin/main HEAD

# 1. A push that introduces two files: one derivation, shared by every routed step.
git -C "${scratch}/work" switch -q -c feature
printf 'one\n' >"${scratch}/work/one.txt"
printf 'two\n' >"${scratch}/work/two.txt"
git -C "${scratch}/work" add -A
git -C "${scratch}/work" -c commit.gpgsign=false commit -qm "feature"
push "${scratch}/work" push -q origin feature || fail "the feature push must pass"
derivations="$(grep -c derive "${scratch}/derivations" || true)"
[[ "${derivations}" -eq 1 ]] || fail "the push must ask for the introduced set once, asked ${derivations} time(s)"
routed="$(grep -c 'candidate file(s) introduced by this push' "${scratch}/push.txt" || true)"
[[ "${routed}" -ge 3 ]] || fail "every routed step must share the one derivation, only ${routed} ran"
grep -q 'dev-profile-push-files: 2 file(s) introduced by this push' "${scratch}/push.txt" ||
	fail "the derivation must report the introduced files"
grep -q '2 of 3 candidate file(s) introduced by this push' "${scratch}/push.txt" ||
	fail "a routed step must judge the files the push introduced"

# 2. The same tip under a new branch name, with its content already on the
# default branch: nothing is introduced, so no routed tool runs, and the push
# still asks for the set exactly once.
git -C "${scratch}/work" update-ref refs/remotes/origin/main "$(git -C "${scratch}/work" rev-parse HEAD)"
push "${scratch}/work" push -q origin feature:copy || fail "a push that introduces nothing must pass"
derivations="$(grep -c derive "${scratch}/derivations" || true)"
[[ "${derivations}" -eq 2 ]] || fail "two pushes must derive the set twice, asked ${derivations} time(s)"
if grep -q 'running hk util' "${scratch}/push.txt"; then
	fail "an inherited push must run no routed tool"
fi

echo "ok introduced-once fixture"
