#!/usr/bin/env bash
# dev-profile-foxguard-introduced is the push gate's foxguard step: it scans
# only the files a push introduces and reports only the findings those files
# introduce, so what the common ancestor carried stays suppressed and no
# untouched file is opened at all. Real foxguard; skips when it is not
# installed. Usage: foxguard-introduced-fixture.sh <generated-dir>
set -euo pipefail

out="$(cd "${1:?usage: foxguard-introduced-fixture.sh <generated-dir>}" && pwd -P)"
# An installed helper is exercised when the directory has one; an empty
# directory exercises this checkout's source helper.
helper="${out}/bin/dev-profile-foxguard-introduced"
[[ -x ${helper} ]] || helper="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)/bin/dev-profile-foxguard-introduced"
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

# Shifting an inherited finding's line does not introduce it.
printf '\n\n' >legacy.ts
git show HEAD:legacy.ts >>legacy.ts
gate legacy.ts
[[ ${status} -eq 0 ]] || fail "line-shifted inherited findings must pass, got ${status}: $(cat "${work}/out" "${work}/err")"
git restore legacy.ts

# Git can publish a branch other than the checkout. Findings in the checkout
# are not part of that push, and findings in the outgoing branch must not hide.
push_refs="${work}/push-refs"
zero="0000000000000000000000000000000000000000"
printf 'export const checkoutOnly = () => dangerouslyRun("checkout-only");\n' >>legacy.ts
printf 'refs/heads/clean %s refs/heads/clean %s\n' "$(git rev-parse clean)" "${zero}" >"${push_refs}"
DEV_PROFILE_PUSH_REFS="${push_refs}" gate legacy.ts
[[ ${status} -eq 0 ]] || fail "a clean outgoing branch must ignore checkout findings, got ${status}: $(cat "${work}/out" "${work}/err")"
pack="../pack.json" DEV_PROFILE_PUSH_REFS="${push_refs}" gate legacy.ts
[[ ${status} -eq 0 ]] || fail "relative rule packs must retain caller resolution, got ${status}: $(cat "${work}/out" "${work}/err")"
printf 'refs/heads/topic %s refs/heads/topic %s\n' "$(git rev-parse topic)" "${zero}" >"${push_refs}"
DEV_PROFILE_PUSH_REFS="${push_refs}" gate legacy.ts added.ts
[[ ${status} -eq 1 ]] || fail "findings in a nonchecked-out outgoing branch must block, got ${status}: $(cat "${work}/out" "${work}/err")"
grep -q 'introduced' "${work}/out" || fail "the outgoing branch finding was not reported"
grep -q 'checkout-only' "${work}/out" && fail "an unrelated checkout finding was reported"
# Multiple outgoing refs are independent; a clean last ref cannot erase a
# finding in an earlier ref. Deletes send no source, malformed refs fail closed.
printf 'refs/heads/clean %s refs/heads/clean %s\n' "$(git rev-parse clean)" "${zero}" >>"${push_refs}"
DEV_PROFILE_PUSH_REFS="${push_refs}" gate legacy.ts added.ts
[[ ${status} -eq 1 ]] || fail "a new finding in any outgoing ref must block, got ${status}"
printf 'refs/heads/deleted %s refs/heads/deleted %s\n' "${zero}" "$(git rev-parse clean)" >"${push_refs}"
DEV_PROFILE_PUSH_REFS="${push_refs}" gate legacy.ts
[[ ${status} -eq 0 ]] || fail "a ref deletion must not scan the checkout, got ${status}"
printf 'malformed refs\n' >"${push_refs}"
DEV_PROFILE_PUSH_REFS="${push_refs}" gate legacy.ts
[[ ${status} -eq 2 ]] || fail "malformed push refs must fail closed, got ${status}"
DEV_PROFILE_PUSH_REFS="${work}/missing-refs" gate legacy.ts
[[ ${status} -eq 2 ]] || fail "unreadable push refs must fail closed, got ${status}"
git restore legacy.ts

# Upstream rewrote the old code after this branch forked. Its deleted/moved
# findings are still inherited by the branch, not introduced by it.
chmod 644 untouched.ts
ancestor="$(git rev-parse HEAD)"
git switch -q -c rewritten-target
git mv legacy.ts moved-legacy.ts
git rm -q untouched.ts
git commit -q -m "upstream rewrites old paths"
git update-ref refs/remotes/origin/main HEAD
git switch -q clean
git commit -q --allow-empty -m "branch diverges from rewritten upstream"
gate legacy.ts untouched.ts
[[ ${status} -eq 0 ]] || fail "findings inherited from the common ancestor must pass after upstream moves/deletes them, got ${status}: $(cat "${work}/out" "${work}/err")"
printf 'export const added = () => dangerouslyRun("diverged-new");\n' >diverged-new.ts
gate legacy.ts untouched.ts diverged-new.ts
[[ ${status} -eq 1 ]] || fail "a genuinely new finding on a diverged branch must block, got ${status}: $(cat "${work}/out" "${work}/err")"
grep -q 'diverged-new' "${work}/out" || fail "the diverged branch's new finding was not reported"
grep -qE 'legacy-fixed|untouched-fixed' "${work}/out" && fail "upstream rewriting old code made inherited findings look introduced"
rm diverged-new.ts
git update-ref refs/remotes/origin/main "${ancestor}"
# A target with none of the new files has zero findings, not empty invalid JSON.
printf 'export const addedOnly = () => dangerouslyRun("new-only");\n' >new-only.ts
gate new-only.ts
[[ ${status} -eq 1 ]] || fail "an all-new input must be compared, got ${status}: $(cat "${work}/err")"
grep -q new-only "${work}/out" || fail "the all-new finding was not reported"
rm new-only.ts

# A target the repository does not have, and a call without one, fail closed.
gate --target origin/nope legacy.ts
[[ ${status} -eq 2 ]] || fail "an unknown target must fail closed, got ${status}"
unrelated="$(git commit-tree "HEAD^{tree}" -m "unrelated target")"
git update-ref refs/remotes/origin/unrelated "${unrelated}"
gate --target origin/unrelated legacy.ts
[[ ${status} -eq 2 ]] || fail "a target without a common ancestor must fail closed, got ${status}"
grep -q 'could not find a common ancestor' "${work}/err" || fail "missing ancestry must explain why the baseline is unavailable"
set +e
"${helper}" --rules "${pack}" legacy.ts >"${work}/out" 2>"${work}/err"
status=$?
set -e
[[ ${status} -eq 2 ]] || fail "a call without --target must fail closed, got ${status}"
grep -q 'usage:' "${work}/err" || fail "a call without --target must explain itself"

# A file foxguard cannot parse at the target contributes no findings there, and
# only that file: findings the target's parseable files carry stay suppressed.
# `export const = (;` is invalid TypeScript, which foxguard skips as a parse error. (This
# fixture once used `export type * from`; the zachbornheimer/foxguard fork the profile
# pins parses that, so it no longer exercised the skip.)
git switch -q -c unparseable-target origin/main
printf 'export const = (;\n' >skipped.ts
git add skipped.ts
git commit -q -m "target with an unparseable file"
git update-ref refs/remotes/origin/unparseable-target HEAD
git switch -q -c parseable-branch
gate_unparseable_target() { gate --target origin/unparseable-target "$@"; }

printf 'export const parsed = 1;\n' >skipped.ts
gate_unparseable_target skipped.ts
[[ ${status} -eq 0 ]] || fail "a clean branch over an unparseable target file must pass, got ${status}: $(cat "${work}/out" "${work}/err")"

printf 'export const parsed = () => dangerouslyRun("newly-parseable");\n' >skipped.ts
gate_unparseable_target skipped.ts
[[ ${status} -eq 1 ]] || fail "a finding in a newly parseable file must be introduced, got ${status}: $(cat "${work}/out" "${work}/err")"
grep -q 'newly-parseable' "${work}/out" || fail "the newly parseable file's finding was not reported: $(cat "${work}/out")"

printf 'export const parsed = 1;\n' >skipped.ts
gate_unparseable_target legacy.ts skipped.ts
[[ ${status} -eq 0 ]] || fail "a parseable target file's finding must stay suppressed beside an unparseable one, got ${status}: $(cat "${work}/out" "${work}/err")"
grep -q 'legacy-fixed' "${work}/out" && fail "a finding the target's parseable file carries was reported"

# The branch breaks the parse of a file the target scans: only the branch skipped it.
printf 'export const = (;\n' >legacy.ts
gate_unparseable_target legacy.ts
[[ ${status} -eq 2 ]] || fail "an unparseable branch file must fail closed, got ${status}: $(cat "${work}/out" "${work}/err")"

# Inherited parse failures remain informational rather than blocking.
printf 'export const = (;\n' >skipped.ts
gate_unparseable_target skipped.ts
[[ ${status} -eq 0 ]] || fail "an inherited skipped file must pass, got ${status}: $(cat "${work}/out" "${work}/err")"
grep -q 'not scanned on the common ancestor either' "${work}/err" || fail "an inherited skipped file must be reported"
echo "ok foxguard-introduced fixture"
