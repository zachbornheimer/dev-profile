#!/usr/bin/env bash
# dev-profile-omp-sync rebuilds omp-build from upstream main plus the configured
# branches on every run, and a conflict installs nothing. Local bare repos stand
# in for upstream and the fork; a stub build stands in for bun. No network.
set -euo pipefail

src="$(cd "$(dirname "$0")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL omp-sync fixture: $*" >&2
	[ ! -f "$work/sync.log" ] || tail -20 "$work/sync.log" >&2
	exit 1
}

# Hermetic git: no user hooks, signing, or identity from the real machine.
export GIT_CONFIG_GLOBAL="$work/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "$GIT_CONFIG_GLOBAL" user.name fixture
git config --file "$GIT_CONFIG_GLOBAL" user.email fixture@example.invalid
git config --file "$GIT_CONFIG_GLOBAL" commit.gpgsign false
git config --file "$GIT_CONFIG_GLOBAL" init.defaultBranch main

export OMP_REPO_DIR="$work/repo" OMP_BUILD_DIR="$work/build" OMP_REBUILD_CONFIG="$work/omp-rebuild.toml"
export OMP_SYNC_LOG="$work/sync.log" OMP_INSTALL_PATH="$work/bin/omp" OMP_NATIVES_CACHE="$work/natives"
# The stub "binary" reports the commit it was built from.
export OMP_SYNC_BUILD_CMD='mkdir -p packages/coding-agent/dist && printf "#!/bin/sh\necho omp/$(git rev-parse --short HEAD)\n" >packages/coding-agent/dist/omp && chmod +x packages/coding-agent/dist/omp'
run_sync() { "$src/bin/dev-profile-omp-sync" >>"$work/sync.out" 2>&1; }
configure() { printf 'branches = [\n%s]\n' "$(printf '  "%s",\n' "$@")" >"$OMP_REBUILD_CONFIG"; }
commit_file() { # <repo> <file> <content> <message>
	printf '%s\n' "$3" >"$1/$2"
	git -C "$1" add "$2"
	git -C "$1" commit -qm "$4"
}

# Upstream with a shared file, a fork, and a local clone wired like the real one.
git init -q --bare "$work/upstream.git"
git init -q --bare "$work/fork.git"
git init -q "$work/seed"
commit_file "$work/seed" shared.txt base "upstream base"
git -C "$work/seed" push -q "$work/upstream.git" main
git clone -q -o fork "$work/fork.git" "$OMP_REPO_DIR" 2>/dev/null
git -C "$OMP_REPO_DIR" remote add origin "$work/upstream.git"
git -C "$OMP_REPO_DIR" fetch -q origin
git -C "$OMP_REPO_DIR" switch -q -c main origin/main

topic() { # <branch> <file> <content>: a topic branch off upstream main, pushed to the fork
	git -C "$OMP_REPO_DIR" switch -q -c "$1" origin/main
	commit_file "$OMP_REPO_DIR" "$2" "$3" "$1"
	git -C "$OMP_REPO_DIR" push -q fork "$1"
	git -C "$OMP_REPO_DIR" switch -q main
}
topic feat/a a.txt "from a"
topic feat/b shared.txt "from b"
topic feat/c shared.txt "from c"

contains() { git -C "$OMP_REPO_DIR" merge-base --is-ancestor "$1" omp-build; }

# 1. Clean branches merge onto upstream and the build is installed.
configure feat/a feat/b
run_sync || fail "clean sync exited non-zero"
contains origin/main && contains feat/a && contains feat/b || fail "omp-build lacks upstream or a configured branch"
[ "$("$OMP_INSTALL_PATH")" = "omp/$(git -C "$OMP_REPO_DIR" rev-parse --short omp-build)" ] || fail "installed binary is not built from omp-build"
[ "$(cat "$work/bin/.omp-sha")" = "$(git -C "$OMP_REPO_DIR" rev-parse omp-build)" ] || fail ".omp-sha does not name omp-build"

# 2. Upstream moves on: the next run is based on the new upstream, never a stale base.
commit_file "$work/seed" upstream-new.txt new "upstream moves"
git -C "$work/seed" push -q "$work/upstream.git" main
run_sync || fail "sync after upstream moved exited non-zero"
git -C "$OMP_REPO_DIR" fetch -q origin
contains origin/main || fail "omp-build was not rebuilt on the new upstream"
[ "$(git -C "$OMP_REPO_DIR" rev-parse main)" = "$(git -C "$OMP_REPO_DIR" rev-parse origin/main)" ] || fail "main was not fast-forwarded to upstream"

# 3. A conflicting branch fails loudly and installs nothing.
before_bin="$("$OMP_INSTALL_PATH")"
before_ref="$(git -C "$OMP_REPO_DIR" rev-parse omp-build)"
configure feat/a feat/b feat/c
if run_sync; then fail "conflicting branch exited zero"; fi
grep -q "FAILED: feat/c conflicts" "$OMP_SYNC_LOG" || fail "failure does not name the conflicting branch"
grep -q "  shared.txt" "$OMP_SYNC_LOG" || fail "failure does not name the conflicting file"
[ "$("$OMP_INSTALL_PATH")" = "$before_bin" ] || fail "a failed sync replaced the installed binary"
[ "$(git -C "$OMP_REPO_DIR" rev-parse omp-build)" = "$before_ref" ] || fail "a failed sync moved omp-build"

# 4. A resolution recorded once is replayed: the next run succeeds unattended.
(
	cd "$OMP_BUILD_DIR"
	git merge -q feat/c >/dev/null 2>&1 || true
	printf 'from b and c\n' >shared.txt
	git add shared.txt
	git commit -q --no-edit >/dev/null 2>&1
)
run_sync || fail "sync with a recorded resolution exited non-zero"
contains feat/c || fail "omp-build lacks the resolved branch"
[ "$(git -C "$OMP_REPO_DIR" show omp-build:shared.txt)" = "from b and c" ] || fail "recorded resolution was not replayed"

# 5. omp-build checked out elsewhere is refused instead of desynced.
git -C "$OMP_REPO_DIR" switch -q omp-build
if run_sync; then fail "sync ran while omp-build was checked out"; fi
grep -q "omp-build is checked out in" "$OMP_SYNC_LOG" || fail "refusal does not say where omp-build is checked out"
git -C "$OMP_REPO_DIR" switch -q main

# 6. A build missing a required feature is refused before anything is installed.
before_bin="$("$OMP_INSTALL_PATH")"
printf 'branches = ["feat/a"]\nrequired_in_tree = ["SESSIONS_DB_URL"]\n' >"$OMP_REBUILD_CONFIG"
if run_sync; then fail "build without a required feature exited zero"; fi
grep -q "lacks required 'SESSIONS_DB_URL'" "$OMP_SYNC_LOG" || fail "refusal does not name the missing feature"
[ "$("$OMP_INSTALL_PATH")" = "$before_bin" ] || fail "a build missing a required feature was installed"

echo "ok omp-sync fixture"
