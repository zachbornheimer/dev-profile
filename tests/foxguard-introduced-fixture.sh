#!/usr/bin/env bash
# dev-profile-foxguard-introduced is the push gate's foxguard step: it scans
# only the files a push introduces and reports only the findings those files
# introduce, so what the target already carried stays suppressed and no
# untouched file is opened at all. Real foxguard; skips when it is not
# installed. Usage: foxguard-introduced-fixture.sh <generated-dir>
set -euo pipefail

out="$(cd "${1:?usage: foxguard-introduced-fixture.sh <generated-dir>}" && pwd -P)"
helper="${out}/bin/dev-profile-foxguard-introduced"
command -v foxguard >/dev/null 2>&1 || {
	echo "foxguard fixture skipped: foxguard not installed"
	exit 0
}

work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'chmod -R u+rwX "${work}" 2>/dev/null || true; rm -rf "${work}"' EXIT
fail() {
	echo "FAIL foxguard-introduced fixture: $*" >&2
	exit 1
}

export GIT_CONFIG_GLOBAL="${work}/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "${GIT_CONFIG_GLOBAL}" user.name fixture
git config --file "${GIT_CONFIG_GLOBAL}" user.email fixture@example.invalid
git config --file "${GIT_CONFIG_GLOBAL}" commit.gpgsign false
export HK=0

pack="${work}/pack.json"
cat >"${pack}" <<'JSON'
{ "rules": [ { "id": "fixture.dangerous-run", "message": "dangerouslyRun executes a string", "severity": "MEDIUM", "languages": ["typescript", "javascript"], "pattern": "dangerouslyRun(...)" } ] }
JSON

repo="${work}/repo"
git init -q -b main "${repo}"
cd "${repo}"
printf 'export const legacy = () => dangerouslyRun("legacy-fixed");\n' >legacy.ts
printf 'export const untouched = () => dangerouslyRun("untouched-fixed");\n' >untouched.ts
for i in $(seq 1 300); do printf 'export const v%d = %d;\n' "${i}" "${i}" >"unrelated${i}.ts"; done
git add -A
git commit -q -m main
git update-ref refs/remotes/origin/main HEAD

git switch -q -c topic
printf 'export const legacy = () => dangerouslyRun("legacy-fixed");\nexport const added = () => dangerouslyRun("introduced");\n' >legacy.ts
printf 'export const added = () => dangerouslyRun("introduced");\n' >added.ts
git add -A
git commit -q -m topic

gate() {
	set +e
	"${helper}" --rules "${pack}" --target origin/main "$@" >"${work}/out" 2>"${work}/err"
	status=$?
	set -e
}

# The finding the branch introduces is reported, and it is the only one: the
# finding the target already carries in the same file stays suppressed.
gate legacy.ts added.ts
[[ ${status} -eq 1 ]] || fail "an introduced finding must exit 1, got ${status}: $(cat "${work}/err")"
grep -q 'introduced' "${work}/out" || fail "the introduced finding was not reported: $(cat "${work}/out")"
grep -q 'legacy-fixed' "${work}/out" && fail "a finding the target already carries was reported"
grep -q 'untouched-fixed' "${work}/out" && fail "a file the push did not introduce was scanned"

# Neither side scans the tree: an untouched file the scan never opens cannot
# fail it, even unreadable.
chmod 000 untouched.ts
gate legacy.ts added.ts
[[ ${status} -eq 1 ]] || fail "an unreadable untouched file must not reach the scan, got ${status}: $(cat "${work}/out" "${work}/err")"

! grep -qiE 'permission denied|cannot read file|scan incomplete' "${work}/out" "${work}/err" ||
	fail "the step's scan reported an unreadable file it should never open"
# The whole-tree scan foxguard's own diff runs does open that file and reports
# it unreadable; the step's scan never opened it. That difference is the fix.
set +e
foxguard diff --rules "${pack}" origin/main >"${work}/control" 2>&1
set -e
grep -qiE 'permission denied|cannot read file|scan incomplete' "${work}/control" ||
	fail "the control scan never hit the unreadable file: $(cat "${work}/control")"

# A push whose files introduce nothing passes, and no file at all runs nothing.
git switch -q -c clean origin/main
gate legacy.ts
[[ ${status} -eq 0 ]] || fail "an unchanged file must pass, got ${status}: $(cat "${work}/out")"
gate
[[ ${status} -eq 0 ]] || fail "no file must pass, got ${status}"
[[ ! -s "${work}/out" && ! -s "${work}/err" ]] || fail "no file must run nothing"

# A target the repository does not have, and a call without one, fail closed.
gate --target origin/nope legacy.ts
[[ ${status} -eq 2 ]] || fail "an unknown target must fail closed, got ${status}"
set +e
"${helper}" --rules "${pack}" legacy.ts >"${work}/out" 2>"${work}/err"
status=$?
set -e
[[ ${status} -eq 2 ]] || fail "a call without --target must fail closed, got ${status}"
grep -q 'usage:' "${work}/err" || fail "a call without --target must explain itself"

echo "ok foxguard-introduced fixture"
