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
run() {
	(cd "${work}/$1" && dev-profile-cargo-deny-introduced licenses bans sources) >"${work}/out.txt" 2>&1
}
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

# 5. A base commit that carries a mise.toml. cargo is a mise shim; an unpacked
# copy is not a trusted checkout, and a config there that is neither ignored nor
# trusted makes the shim exit the way the real one does ("Config files in
# <dir>/mise.toml are not trusted"), so cargo-deny never finishes. The base run
# must finish anyway. The inherited license stays pre-existing; a license the
# push adds still fails. The stub stands in only while the gate runs, so the
# real cargo still locks the crate. The stub stands in for the mise shim, so
# it execs the real binary the shim fronts: the first cargo on PATH that is not
# a mise shim.
real_cargo=""
while IFS= read -r candidate; do
	if [[ -n "${candidate}" && "${candidate}" != */mise/shims/* ]]; then
		real_cargo="${candidate}"
		break
	fi
done < <(type -ap cargo 2>/dev/null || true)
[[ -n "${real_cargo}" && -x "${real_cargo}" ]] || fail "could not find a cargo that is not the mise shim"
real_deny="$(command -v cargo-deny)"
stubs="${work}/stubs"
mkdir -p "${stubs}"
cat >"${stubs}/cargo" <<STUB
#!/usr/bin/env bash
set -euo pipefail
# A checkout is trusted: its mise config is already on the machine. The unpacked
# base is a temp copy, and a mise config there that is neither ignored nor trusted
# fails the way the real shim does. Ignoring or trusting that directory lets the
# real cargo run.
dir="\$(pwd -P)"
case "\${dir}" in
"${work}"/*) ;;
*)
	while [[ "\${dir}" != / ]]; do
		if [[ -f "\${dir}/mise.toml" || -f "\${dir}/.mise.toml" || -f "\${dir}/mise/config.toml" || -f "\${dir}/.config/mise.toml" || -f "\${dir}/.tool-versions" ]]; then
			case ":\${MISE_IGNORED_CONFIG_PATHS-}:\${MISE_TRUSTED_CONFIG_PATHS-}:" in
			*":\${dir}:"*) ;;
			*)
				echo "mise ERROR Config files in \${dir}/mise.toml are not trusted." >&2
				exit 1
				;;
			esac
			break
		fi
		dir="\$(dirname "\${dir}")"
	done
	;;
esac
exec "${real_cargo}" "\$@"
STUB
cat >"${stubs}/cargo-deny" <<STUB
#!/usr/bin/env bash
set -euo pipefail
# cargo-deny asks the shim for the crate graph before it reports anything. An
# untrusted config fails that ask, so the diagnostic is the trust error and the
# real checker never runs. A trusted or ignored config falls through.
if ! "${stubs}/cargo" metadata --offline --format-version 1 >/dev/null; then
	exit 1
fi
exec "${real_deny}" "\$@"
STUB
chmod +x "${stubs}/cargo" "${stubs}/cargo-deny"
repo_with_base e GPL-3.0-only
# repo_with_base leaves one commit, and that commit is the base. Amend the
# mise.toml onto it and push; the source edit is a new commit on top, so HEAD
# and the base differ by that change only.
printf '[tools]\npython = "3.12.11"\n' >"${work}/e/mise.toml"
git -C "${work}/e" add mise.toml
git -C "${work}/e" commit -q --amend --no-edit
git -C "${work}/e" push -qf origin HEAD:main
printf 'fn main() { println!("fork"); }\n' >"${work}/e/src/main.rs"
commit e "feat: print fork"
PATH="${stubs}:${PATH}" run e || fail "a mise.toml on the base must not stop the base run"
expect_out "0 introduced, 1 pre-existing" "untrusted mise.toml"
expect_no_out "did not finish" "untrusted mise.toml"
expect_no_out "not trusted" "untrusted mise.toml"
sed 's/^license = .*/license = "AGPL-3.0-only"/' "${work}/e/Cargo.toml" >"${work}/e/Cargo.toml.new"
mv "${work}/e/Cargo.toml.new" "${work}/e/Cargo.toml"
(cd "${work}/e" && "${real_cargo}" generate-lockfile --offline) >"${work}/out.txt" 2>&1 || fail "could not relock e"
commit e "chore: relicense"
if PATH="${stubs}:${PATH}" run e; then fail "a license the push introduces must still fail when the base carries a mise.toml"; fi
expect_out "errors introduced by this push" "introduced over mise.toml"
expect_out "[rejected] fixture" "introduced over mise.toml"
expect_no_out "did not finish" "introduced over mise.toml"

echo "cargo-deny-introduced fixture ok"
