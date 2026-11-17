#!/usr/bin/env bash
# dev-profile-cargo-deny-introduced blocks a push only on the cargo-deny errors it
# introduces. cargo-deny judges the whole crate graph, never the pushed files, so a
# crate whose license the profile's allow-list lacks failed every push to a fork that
# inherited it (zachbornheimer/hexyl, 2026-11-17: 46 license rejections and one
# advisory, all already on sharkdp/hexyl's master). The base's errors are printed as
# pre-existing, never hidden; an error the base lacks fails the push. Real cargo-deny
# and cargo, offline: dependency-free crates, checks narrowed to licenses, bans and
# sources (the advisory database needs the network). Usage: cargo-deny-introduced-fixture.sh
set -euo pipefail
command -v cargo-deny >/dev/null 2>&1 || exit 0
command -v cargo >/dev/null 2>&1 || exit 0

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL cargo-deny-introduced: $*" >&2
	[[ ! -f "${work}/out.txt" ]] || sed 's/^/  | /' "${work}/out.txt" >&2
	exit 1
}

export GIT_CONFIG_GLOBAL="${work}/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "${GIT_CONFIG_GLOBAL}" user.name fixture
git config --file "${GIT_CONFIG_GLOBAL}" user.email fixture@example.invalid
git config --file "${GIT_CONFIG_GLOBAL}" commit.gpgsign false
export PATH="${repo}/bin:${PATH}"

# The profile's deny.toml one directory above every repository, as
# ~/Developer/Personal/deny.toml is above every checkout under it.
cp "${repo}/config/deny.toml" "${work}/deny.toml"

crate() { # <dir> <license>: a dependency-free crate under that license, locked
	mkdir -p "$1/src"
	printf '[package]\nname = "fixture"\nversion = "0.1.0"\nedition = "2021"\nlicense = "%s"\n' "$2" >"$1/Cargo.toml"
	printf 'fn main() {}\n' >"$1/src/main.rs"
	(cd "$1" && cargo generate-lockfile --offline) >"${work}/out.txt" 2>&1 || fail "could not lock $1"
}

# repo_with_base <name> <license> [mirror]: a repo whose origin/<mirror> (default main)
# holds a crate under <license>, switched to a feature branch for the change under test.
repo_with_base() {
	local dir="${work}/$1" mirror="${3:-main}"
	git init -q --bare "${work}/$1.git"
	git init -q -b "${mirror}" "${dir}"
	git -C "${dir}" remote add origin "${work}/$1.git"
	crate "${dir}" "$2"
	git -C "${dir}" add -A
	git -C "${dir}" commit -qm "chore: base"
	git -C "${dir}" push -q origin "${mirror}"
	git -C "${dir}" fetch -q origin
	git -C "${dir}" symbolic-ref "refs/remotes/origin/HEAD" "refs/remotes/origin/${mirror}"
	git -C "${dir}" switch -q -c feature
}
commit() { # <name> <message>
	git -C "${work}/$1" add -A
	git -C "${work}/$1" commit -qm "$2"
}
# run <name>: the gate from the workspace root, as hk's dir = "{{workspace}}" runs it.
run() { (cd "${work}/$1" && dev-profile-cargo-deny-introduced licenses bans sources) >"${work}/out.txt" 2>&1; }
expect_out() { grep -qF -- "$1" "${work}/out.txt" || fail "$2: output must contain: $1"; }
expect_no_out() { ! grep -qF -- "$1" "${work}/out.txt" || fail "$2: output must not contain: $1"; }

# 1. A license the base already carries does not fail a push that only edits source,
# and it stays visible as pre-existing.
repo_with_base a GPL-3.0-only
printf 'fn main() { println!("fork"); }\n' >"${work}/a/src/main.rs"
commit a "feat: print fork"
run a || fail "an inherited license rejection must not fail the push"
expect_out "0 introduced, 1 pre-existing" "inherited"
expect_out "[rejected] fixture" "inherited"
expect_no_out "errors introduced by this push" "inherited"

# 2. A license the push introduces fails it.
repo_with_base b MIT
sed 's/^license = .*/license = "GPL-3.0-only"/' "${work}/b/Cargo.toml" >"${work}/b/Cargo.toml.new"
mv "${work}/b/Cargo.toml.new" "${work}/b/Cargo.toml"
commit b "chore: relicense"
if run b; then fail "a license rejection the push introduces must fail it"; fi
expect_out "errors introduced by this push" "introduced"
expect_out "[rejected] fixture" "introduced"

# 3. A fork whose default branch (origin/HEAD) is an orphan config branch shares no
# history with the work: the mirror it was cut from is the base.
repo_with_base c GPL-3.0-only master
git -C "${work}/c" switch -q --orphan fork
printf 'carry\n' >"${work}/c/branches"
git -C "${work}/c" add branches
git -C "${work}/c" commit -qm "ci: fork config"
git -C "${work}/c" push -q origin fork
git -C "${work}/c" fetch -q origin
git -C "${work}/c" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/fork
git -C "${work}/c" switch -q feature
printf 'fn main() { println!("fork"); }\n' >"${work}/c/src/main.rs"
commit c "feat: print fork"
run c || fail "an orphan default branch must fall through to the mirror as the base"
expect_out "0 introduced, 1 pre-existing" "orphan default"
expect_no_out "no upstream default branch" "orphan default"

# 4. With no upstream default branch nothing can be called pre-existing.
repo_with_base d GPL-3.0-only
git -C "${work}/d" symbolic-ref --delete refs/remotes/origin/HEAD
git -C "${work}/d" update-ref -d refs/remotes/origin/main
if run d; then fail "without a base every error is introduced and must fail the push"; fi
expect_out "no upstream default branch" "no base"
expect_out "errors introduced by this push" "no base"

echo "cargo-deny-introduced fixture ok"
