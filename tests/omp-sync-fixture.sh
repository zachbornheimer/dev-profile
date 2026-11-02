#!/usr/bin/env bash
# dev-profile-omp-sync builds from a fresh temp clone of upstream main plus the
# configured fork branches and never mutates the user's oh-my-pi checkout. Proven
# here: a merge conflict (or a configured branch missing on the fork) fails
# loudly without installing or pushing anything, the success path installs via
# OMP_SYNC_INSTALL_DIR, an unchanged build tree skips the build as "up to date",
# and --push is lease-protected. Real git against local remotes (URL rewrite);
# `bun` is a stub that records calls and fakes the build.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sync="$root/bin/dev-profile-omp-sync"
[[ -x "$sync" ]] || {
	echo "FAIL omp-sync fixture: missing $sync" >&2
	exit 1
}

work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$work"' EXIT

fail() {
	echo "FAIL omp-sync fixture: $*" >&2
	if [[ -n "${RUN_OUT:-}" && -f "$RUN_OUT" ]]; then
		sed 's/^/  | /' "$RUN_OUT" >&2
		log_file="${RUN_OUT/out-/omp-sync-}"
		log_file="${log_file%.txt}.log"
		if [[ -f "$log_file" ]]; then
			echo "  ! tail of $log_file:" >&2
			tail -n 12 "$log_file" >&2
		fi
	fi
	exit 1
}

export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid

# Global config: identity, no signing, and URL rewrites so the script's hardcoded
# GitHub remotes resolve to the local bare repos below (no network in this test).
gitconfig="$work/gitconfig"
git config --file "$gitconfig" user.name fixture
git config --file "$gitconfig" user.email fixture@example.invalid
git config --file "$gitconfig" commit.gpgsign false
git config --file "$gitconfig" url."file://$work/upstream.git".insteadOf https://github.com/can1357/oh-my-pi.git
git config --file "$gitconfig" url."file://$work/fork.git".insteadOf https://github.com/zachbornheimer/oh-my-pi.git
export GIT_CONFIG_GLOBAL="$gitconfig"

# upstream: main moves a.txt from "one" to "two". fork: feat/ok adds b.txt on top
# of the "one" commit (merges clean), feat/conflict rewrites a.txt (merges dirty),
# and omp-build trails at the "one" commit.
git init -q --bare "$work/upstream.git"
git init -q --bare "$work/fork.git"
git init -q -b main "$work/seed"
echo one >"$work/seed/a.txt"
# The natives package version keys the addon cache lookup (~/.omp/natives/<ver>);
# version-sentinel.js is the release-identity check the sync validates with.
mkdir -p "$work/seed/packages/natives/native"
printf '{\n  "name": "pi-natives-fixture",\n  "version": "fixture"\n}\n' >"$work/seed/packages/natives/package.json"
cat >"$work/seed/packages/natives/native/version-sentinel.js" <<'JS'
// Test double of packages/natives/native/version-sentinel.js: same contract the
// sync's addon validation calls.
export function containsVersionStamp(bytes, version) {
	const needle = Buffer.from(`PI_NATIVES_VERSION_STAMP:${version}\0`, "utf8");
	return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).indexOf(needle) !== -1;
}
export function containsLegacyVersionSentinel(bytes, version) {
	const needle = Buffer.from(`__piNativesV${version.replace(/[^A-Za-z0-9]/g, "_")}`, "utf8");
	return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).indexOf(needle) !== -1;
}
JS
git -C "$work/seed" add a.txt packages
git -C "$work/seed" commit -qm "feat: base"
git -C "$work/seed" branch feat/ok
git -C "$work/seed" branch feat/conflict
echo two >"$work/seed/a.txt"
git -C "$work/seed" commit -q -a -m "feat: upstream moves a.txt"
git -C "$work/seed" checkout -q feat/conflict
echo branch >"$work/seed/a.txt"
git -C "$work/seed" commit -q -a -m "feat: conflicting topic"
git -C "$work/seed" checkout -q feat/ok
echo ok >"$work/seed/b.txt"
git -C "$work/seed" add b.txt
git -C "$work/seed" commit -qm "feat: ok topic"
git -C "$work/seed" branch old-build main~1
git -C "$work/seed" remote add upstream "file://$work/upstream.git"
git -C "$work/seed" remote add fork "file://$work/fork.git"
git -C "$work/seed" push -q upstream main
git -C "$work/seed" push -q fork feat/ok feat/conflict main old-build:omp-build
upstream_main="$(git --git-dir="$work/upstream.git" rev-parse refs/heads/main)"
ok_sha="$(git -C "$work/seed" rev-parse feat/ok)"

# The user's checkout: only the reference-transaction hook may ever be written.
git init -q -b main "$work/user-repo"
echo keep >"$work/user-repo/keep.txt"
git -C "$work/user-repo" add keep.txt
git -C "$work/user-repo" commit -qm "chore: user work"
user_head="$(git -C "$work/user-repo" rev-parse HEAD)"

# bun stub on the first PATH slot the script exports ($HOME/Developer/.../bin):
# records calls, fakes the compiled binary, delegates `bun -e` to the real bun
# (the addon identity check runs real code), and (case f) moves the fork's build
# branch mid-run to prove the push lease.
mkdir -p "$work/home/Developer/Personal/dev-profile/bin"
cat >"$work/home/Developer/Personal/dev-profile/bin/bun" <<'STUB'
#!/usr/bin/env bash
echo "bun $*" >>"${BUN_LOG:?}"
if [ "${1:-}" = "-e" ]; then
	exec "${FIXTURE_REAL_BUN:?}" "$@"
fi
case "$*" in
*"--cwd=packages/coding-agent run build"*)
	if [ -n "${FIXTURE_SABOTAGE_MARKER:-}" ] && [ -f "${FIXTURE_SABOTAGE_MARKER}" ]; then
		git --git-dir="${FIXTURE_FORK_GIT:?}" update-ref refs/heads/omp-build "${FIXTURE_FORK_OTHER_SHA:?}"
	fi
	mkdir -p packages/coding-agent/dist
	printf '#!/usr/bin/env bash\necho "omp fixture 0.0.0"\n' >packages/coding-agent/dist/omp
	chmod +x packages/coding-agent/dist/omp
	;;
esac
exit 0
STUB
chmod +x "$work/home/Developer/Personal/dev-profile/bin/bun"

# Native addon cache: either platform's pattern matches, and each fake addon
# carries this release's version stamp so the identity check accepts it.
mkdir -p "$work/home/.omp/natives/fixture"
for fake in pi_natives.darwin-arm64.node pi_natives.linux-x64.node; do
	printf 'PI_NATIVES_VERSION_STAMP:fixture' >"$work/home/.omp/natives/fixture/$fake"
	head -c 1 /dev/zero >>"$work/home/.omp/natives/fixture/$fake"
done
export FIXTURE_REAL_BUN
# The mise shim needs the real HOME to resolve tool versions, and the runs fake
# HOME; resolve the real bun binary instead.
FIXTURE_REAL_BUN="$(mise which bun 2>/dev/null || true)"
if [ -z "$FIXTURE_REAL_BUN" ]; then
	FIXTURE_REAL_BUN="$HOME/.bun/bin/bun"
fi
[[ -x "$FIXTURE_REAL_BUN" ]] || {
	echo "FAIL omp-sync fixture: cannot resolve the real bun binary" >&2
	exit 1
}

write_config() {
	local case_name="$1"
	shift
	{
		echo 'upstream_remote = "origin"'
		echo 'upstream_branch = "main"'
		echo 'fork_remote = "fork"'
		echo 'build_branch = "omp-build"'
		echo ""
		echo "branches = ["
		local b
		for b in "$@"; do
			echo "  \"$b\","
		done
		echo "]"
	} >"$work/omp-rebuild-$case_name.toml"
}

run_sync() {
	local case_name="$1"
	shift
	mkdir -p "$work/tmp-$case_name"
	RUN_STATUS=0
	BUN_LOG="$work/bun-$case_name.log" \
		OMP_REPO_DIR="$work/user-repo" \
		OMP_REBUILD_CONFIG="$work/omp-rebuild-$case_name.toml" \
		OMP_SYNC_LOG="$work/omp-sync-$case_name.log" \
		OMP_SYNC_INSTALL_DIR="${RUN_INSTALL_DIR:-$work/install-$case_name}" \
		TMPDIR="$work/tmp-$case_name" \
		HOME="${RUN_HOME:-$work/home}" \
		"$sync" "$@" >"$work/out-$case_name.txt" 2>&1 || RUN_STATUS=$?
	RUN_OUT="$work/out-$case_name.txt"
}

assert_user_repo_clean() {
	local when="$1"
	[[ -z "$(git -C "$work/user-repo" status --porcelain)" ]] || fail "$when: user checkout must stay clean"
	[[ "$(git -C "$work/user-repo" rev-parse HEAD)" == "$user_head" ]] || fail "$when: user checkout HEAD moved"
	[[ -f "$work/user-repo/.git/hooks/reference-transaction" ]] || fail "$when: main-lock hook must be installed"
}

# a) Merge conflict: loud failure naming branch and files; nothing installed,
# nothing pushed, no build run at all.
write_config a feat/conflict
git --git-dir="$work/fork.git" for-each-ref >"$work/fork-refs-before"
run_sync a --push
[[ "$RUN_STATUS" -ne 0 ]] || fail "a: conflict run must exit non-zero"
grep -q "feat/conflict" "$RUN_OUT" || fail "a: conflict report must name the branch"
grep -q "a.txt" "$RUN_OUT" || fail "a: conflict report must name the conflicting file"
[[ ! -e "$work/install-a/omp" ]] || fail "a: conflict run must not install a binary"
[[ ! -s "$work/bun-a.log" ]] || fail "a: conflict run must not build"
git --git-dir="$work/fork.git" for-each-ref >"$work/fork-refs-after-a"
diff "$work/fork-refs-before" "$work/fork-refs-after-a" >/dev/null || fail "a: conflict run must not push"
assert_user_repo_clean "a"

# b) Missing configured branch is an error (no silent skips); --include/--exclude
# edit the config as before; the temp clone is cleaned without --keep.
write_config b feat/gone
run_sync b --include feat/new --exclude feat/gone
[[ "$RUN_STATUS" -ne 0 ]] || fail "b: missing branch must exit non-zero"
grep -q "feat/new" "$RUN_OUT" || fail "b: error must name the missing branch"
grep -q "missing" "$RUN_OUT" || fail "b: error must say the branch is missing"
grep -q '"feat/new"' "$work/omp-rebuild-b.toml" || fail "b: --include must add the branch"
grep -q '"feat/gone"' "$work/omp-rebuild-b.toml" && fail "b: --exclude must remove the branch"
[[ ! -e "$work/install-b/omp" ]] || fail "b: error run must not install a binary"
[[ -z "$(find "$work/tmp-b" -mindepth 1)" ]] || fail "b: temp clone must be removed without --keep"
assert_user_repo_clean "b"

# c) Success path with no topic branches: compiles and installs via
# OMP_SYNC_INSTALL_DIR; the stamp matches upstream main; natives come from cache.
write_config c
run_sync c --keep
[[ "$RUN_STATUS" -eq 0 ]] || fail "c: empty-branch run must succeed"
[[ -x "$work/install-c/omp" ]] || fail "c: binary must be installed"
installed_ver="$("$work/install-c/omp" --version)"
[[ "$installed_ver" == *"omp fixture"* ]] || fail "c: --version must run"
kept_c="$(find "$work/tmp-c" -maxdepth 2 -type d -name oh-my-pi | head -n 1)"
[[ -n "$kept_c" ]] || fail "c: --keep must retain the build dir"
[[ "$(cat "$work/install-c/.omp-sha")" == "$(git -C "$kept_c" rev-parse HEAD)" ]] || fail "c: stamp must match built HEAD"
[[ "$(cat "$work/install-c/.omp-sha")" == "$upstream_main" ]] || fail "c: stamp must match upstream main"
grep -q "bun install" "$work/bun-c.log" || fail "c: bun install must run"
grep -q -- "--cwd=packages/coding-agent run build" "$work/bun-c.log" || fail "c: compile must run"
grep -q -- "--cwd=packages/natives" "$work/bun-c.log" && fail "c: cached natives must skip the native build"
native_in_clone="$(find "$kept_c/packages/natives/native" -name 'pi_natives.*.node')"
[[ -n "$native_in_clone" ]] || fail "c: cached native must be copied in"
assert_user_repo_clean "c"

# d) Success path with a clean topic branch: merged in order and pushed to the
# fork with the lease.
write_config d feat/ok
run_sync d --keep --push
[[ "$RUN_STATUS" -eq 0 ]] || fail "d: clean-branch run must succeed"
kept_d="$(find "$work/tmp-d" -maxdepth 2 -type d -name oh-my-pi | head -n 1)"
[[ -n "$kept_d" ]] || fail "d: --keep must retain the build dir"
merge_log="$(git -C "$kept_d" log --oneline)"
[[ "$merge_log" == *"Merge feat/ok into omp-build"* ]] || fail "d: branch must be merged"
[[ "$(git --git-dir="$work/fork.git" rev-parse refs/heads/omp-build)" == "$(cat "$work/install-d/.omp-sha")" ]] || fail "d: --push must move fork/omp-build to the built sha"
assert_user_repo_clean "d"

# g) Up to date: when the computed tree matches the tree behind the install
# stamp, the build is skipped entirely while --push still moves the fork.
write_config g feat/ok
RUN_INSTALL_DIR="$work/install-d" run_sync g --push
[[ "$RUN_STATUS" -eq 0 ]] || fail "g: up-to-date run must succeed"
grep -q "up to date" "$RUN_OUT" || fail "g: run must report up to date"
[[ ! -s "$work/bun-g.log" ]] || fail "g: up-to-date run must not build"
[[ "$(git --git-dir="$work/fork.git" rev-parse "refs/heads/omp-build^{tree}")" == "$(git --git-dir="$work/fork.git" rev-parse "$(cat "$work/install-d/.omp-sha")^{tree}")" ]] ||
	fail "g: --push must still move fork/omp-build to the computed tree"
assert_user_repo_clean "g"

# h) No cached or prebuilt addon for this natives version: the natives build must
# run rather than silently embedding a mismatched addon.
mkdir -p "$work/home-h/Developer/Personal/dev-profile/bin"
cp "$work/home/Developer/Personal/dev-profile/bin/bun" "$work/home-h/Developer/Personal/dev-profile/bin/bun"
chmod +x "$work/home-h/Developer/Personal/dev-profile/bin/bun"
write_config h
RUN_HOME="$work/home-h" run_sync h
[[ "$RUN_STATUS" -eq 0 ]] || fail "h: build-fallback run must succeed"
grep -q -- "--cwd=packages/natives run build" "$work/bun-h.log" || fail "h: natives must be built when no addon matches"
assert_user_repo_clean "h"

# e) Clean cutover: --compile is gone and --keep exists.
run_sync e --compile
[[ "$RUN_STATUS" -ne 0 ]] || fail "e: --compile must be rejected"
grep -q "Unknown argument" "$RUN_OUT" || fail "e: rejection must say unknown argument"
run_sync ehelp --help
grep -q -- "--keep" "$RUN_OUT" || fail "e: help must document --keep"
grep -q -- "--compile" "$RUN_OUT" && fail "e: help must not mention --compile"

# f) Push lease: the fork's build branch moving mid-run must fail the push.
# --allow-drop: with an empty config the branch commits are uncovered work, and
# this case is about the lease, not the drop guard.
write_config f
FIXTURE_SABOTAGE_MARKER="$work/sabotage.marker"
FIXTURE_FORK_GIT="$work/fork.git"
FIXTURE_FORK_OTHER_SHA="$ok_sha"
export FIXTURE_SABOTAGE_MARKER FIXTURE_FORK_GIT FIXTURE_FORK_OTHER_SHA
: >"$FIXTURE_SABOTAGE_MARKER"
run_sync f --push --allow-drop
[[ "$RUN_STATUS" -ne 0 ]] || fail "f: stale lease must fail the push"
grep -q "lease" "$RUN_OUT" || fail "f: failure must mention the lease"
[[ "$(git --git-dir="$work/fork.git" rev-parse refs/heads/omp-build)" == "$ok_sha" ]] || fail "f: fork must keep the sabotaged sha"
assert_user_repo_clean "f"
rm -f "$FIXTURE_SABOTAGE_MARKER"

# i) fork/omp-build carrying work no branch can recover: --push must refuse and
# print the commits instead of force-overwriting them.
git -C "$work/seed" fetch -q fork "+refs/heads/omp-build:refs/heads/stray-base"
git -C "$work/seed" checkout -q stray-base
echo stray >"$work/seed/stray.txt"
git -C "$work/seed" add stray.txt
git -C "$work/seed" commit -qm "feat: stray work"
git -C "$work/seed" push -q fork "HEAD:refs/heads/omp-build"
stray_tip="$(git -C "$work/seed" rev-parse HEAD)"
git -C "$work/seed" checkout -q feat/ok
write_config i feat/ok
run_sync i --push
[[ "$RUN_STATUS" -ne 0 ]] || fail "i: stray commits must refuse the push"
grep -q "stray work" "$RUN_OUT" || fail "i: refusal must print the stray commits"
grep -q "Refusing to push" "$RUN_OUT" || fail "i: refusal must say it refuses to push"
[[ "$(git --git-dir="$work/fork.git" rev-parse refs/heads/omp-build)" == "$stray_tip" ]] || fail "i: fork/omp-build must not be overwritten"
assert_user_repo_clean "i"

# j) The same stray commits with --allow-drop: reviewed, so the push proceeds.
write_config j feat/ok
run_sync j --push --allow-drop
[[ "$RUN_STATUS" -eq 0 ]] || fail "j: --allow-drop must let the push through"
grep -q "stray work" "$RUN_OUT" || fail "j: --allow-drop must still print the stray commits"
[[ "$(git --git-dir="$work/fork.git" rev-parse refs/heads/omp-build)" == "$(cat "$work/install-j/.omp-sha")" ]] || fail "j: --allow-drop must push the rebuilt branch"
assert_user_repo_clean "j"

# k) A recorded cherry-pick of a configured branch commit is covered work.
git -C "$work/seed" fetch -q fork "+refs/heads/omp-build:refs/heads/stray-base"
git -C "$work/seed" checkout -q stray-base
echo backport >"$work/seed/backport.txt"
git -C "$work/seed" add backport.txt
git -C "$work/seed" commit -qm "feat: backport work

(cherry picked from commit $(git -C "$work/seed" rev-parse feat/ok))"
git -C "$work/seed" push -q fork "HEAD:refs/heads/omp-build"
git -C "$work/seed" checkout -q feat/ok
write_config k feat/ok
run_sync k --push
[[ "$RUN_STATUS" -eq 0 ]] || fail "k: cherry-picked-from configured work must be covered"
[[ "$(git --git-dir="$work/fork.git" rev-parse refs/heads/omp-build)" == "$(cat "$work/install-k/.omp-sha")" ]] || fail "k: covered work must not block the push"
assert_user_repo_clean "k"

# m) A configured branch contained in a later configured branch is merged through
# that branch (c906544 behavior), so its stale copy never conflicts on its own.
git -C "$work/seed" fetch -q fork "+refs/heads/omp-build:refs/heads/stray-base"
git -C "$work/seed" checkout -q stray-base
echo d1 >"$work/seed/d1.txt"
git -C "$work/seed" add d1.txt
git -C "$work/seed" commit -qm "feat: deep one"
git -C "$work/seed" branch feat/shallow
echo d2 >"$work/seed/d2.txt"
git -C "$work/seed" add d2.txt
git -C "$work/seed" commit -qm "feat: deep two"
git -C "$work/seed" branch feat/deep
git -C "$work/seed" push -q fork "feat/shallow:refs/heads/feat/shallow" "feat/deep:refs/heads/feat/deep"
git -C "$work/seed" checkout -q feat/ok
write_config m feat/shallow feat/deep
run_sync m
[[ "$RUN_STATUS" -eq 0 ]] || fail "m: contained-branch run must succeed"
grep -q "Merge feat/shallow: contained in feat/deep" "$RUN_OUT" || fail "m: contained branch must merge through its container"
assert_user_repo_clean "m"

# n) A conflict resolved once in a --keep clone is replayed by rerere on every
# later run: the next sync merges the same branch unattended and installs.
write_config n feat/conflict
run_sync n --keep
[[ "$RUN_STATUS" -ne 0 ]] || fail "n: first conflict run must fail"
kept_n="$(find "$work/tmp-n" -maxdepth 2 -type d -name oh-my-pi | head -n 1)"
[[ -n "$kept_n" ]] || fail "n: --keep must retain the conflicted clone"
echo resolved >"$kept_n/a.txt"
git -C "$kept_n" add a.txt
git -C "$kept_n" commit -q --no-edit
write_config n2 feat/conflict
run_sync n2
[[ "$RUN_STATUS" -eq 0 ]] || fail "n: a recorded resolution must let the rerun succeed"
grep -q "resolved by recorded resolutions" "$RUN_OUT" || fail "n: rerun must report the rerere replay"
[[ -x "$work/install-n2/omp" ]] || fail "n: rerere-resolved build must install"
assert_user_repo_clean "n"
# The same inputs again: up to date without a rebuild, though merge-tree alone
# cannot reproduce a rerere-resolved merge.
write_config n3 feat/conflict
RUN_INSTALL_DIR="$work/install-n2" run_sync n3
[[ "$RUN_STATUS" -eq 0 ]] || fail "n: unchanged inputs must succeed"
grep -q "up to date" "$RUN_OUT" || fail "n: unchanged inputs after a rerere merge must be up to date"
[[ ! -s "$work/bun-n3.log" ]] || fail "n: unchanged inputs must not rebuild"

# o) A merged tree missing a required_in_tree string is refused before anything
# is built or installed.
write_config o feat/ok
printf '\nrequired_in_tree = ["SESSIONS_DB_URL"]\n' >>"$work/omp-rebuild-o.toml"
run_sync o
[[ "$RUN_STATUS" -ne 0 ]] || fail "o: a build missing a required string must fail"
grep -q "lacks required 'SESSIONS_DB_URL'" "$RUN_OUT" || fail "o: refusal must name the missing string"
[[ ! -e "$work/install-o/omp" ]] || fail "o: refused build must not install"
[[ ! -s "$work/bun-o.log" ]] || fail "o: refused build must not run bun"
assert_user_repo_clean "o"

echo "ok omp-sync"
