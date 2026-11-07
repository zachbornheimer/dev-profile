#!/usr/bin/env bash
# `wt step copy-ignored` reflinks the primary worktree's ignored build output
# into a fresh worktree. A branch whose tree carries no ignore rules (a
# tooling branch) has none for that output either, so every copied file shows
# as non-ignored untracked and each hook enumerates and stashes them all.
# dev-profile-worktree-copy must answer with a per-worktree core.excludesFile
# (a per-worktree info/exclude has no effect on this git) holding rules for
# exactly what the copy landed, folded with the global ignore rules the key
# replaces — and nothing at all when the branch's own tree already covers it.
set -euo pipefail
repo="${1:?usage: worktree-copy-excludes-fixture.sh <repo-root>}"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL worktree-copy-excludes: $*" >&2
	exit 1
}

# `git` on PATH is a wrapper that fires the installed hooks, and `wt` resolves
# through the machine's mise shims; drive the real git directly and answer
# `wt step copy-ignored` with a stub that performs the copy it reflinks.
git_bin=""
for candidate in /opt/homebrew/bin/git /usr/bin/git; do
	if [[ -x "${candidate}" ]]; then
		git_bin="${candidate}"
		break
	fi
done
[[ -n "${git_bin}" ]] || fail "no real git binary"
stub_bin="${scratch}/stub-bin"
mkdir -p "${stub_bin}"
ln -s "${git_bin}" "${stub_bin}/git"
cat >"${stub_bin}/wt" <<'EOF'
#!/usr/bin/env bash
# Test stand-in for worktrunk's `wt step copy-ignored`: copy the primary
# worktree's ignored output into this one.
set -euo pipefail
[[ "${1:-} ${2:-}" == "step copy-ignored" ]] || {
	echo "wt stub: unsupported: $*" >&2
	exit 2
}
root="$(git rev-parse --show-toplevel)"
primary="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
[[ "${root}" == "${primary}" ]] && exit 0 # nothing to copy into itself
while IFS= read -r -d '' entry; do
	[[ "${entry:0:2}" == '!!' ]] || continue # not ignored in the primary
	path="${entry:3}"
	path="${path%/}"
	[[ -n "${path}" && -e "${primary}/${path}" ]] || continue
	if [[ "${path}" == */* ]]; then mkdir -p "${root}/${path%/*}"; fi
	cp -R "${primary}/${path}" "${root}/${path}"
done < <(git -C "${primary}" status --porcelain --ignored -z)
EOF
chmod +x "${stub_bin}/wt"
export PATH="${stub_bin}:${repo}/bin:${PATH}"
export GIT_CONFIG_SYSTEM=/dev/null
export GIT_CONFIG_GLOBAL="${scratch}/gitconfig"
export XDG_CONFIG_HOME="${scratch}/xdg"
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
printf '[core]\n\texcludesFile = %s\n' "${scratch}/global-ignore" >"${GIT_CONFIG_GLOBAL}"
printf '.DS_Store\nnode_modules/\n' >"${scratch}/global-ignore"

count_untracked() { # <worktree>
	"${git_bin}" -C "$1" ls-files --others --exclude-standard | wc -l | tr -d ' '
}

# The primary carries the ignore rules and the ignored build output; ci-tooling
# drops the rules (the defect shape), norm-keep keeps them.
primary="${scratch}/primary"
"${git_bin}" init -q -b feature "${primary}"
cd "${primary}"
printf 'target/\npackages/app/dist/\n*.o\n' >.gitignore
mkdir -p src packages/app/src packages/mixed target packages/app/dist node_modules/dep
printf 'export const keep = 1\n' >src/keep.ts
printf 'export const app = 1\n' >packages/app/src.ts
printf 'export const mixed = 1\n' >packages/mixed/keep.ts
printf 'built\n' >target/build.o
printf 'built\n' >packages/app/dist/app.js
printf 'built\n' >packages/mixed/junk.o
printf 'built\n' >node_modules/dep/dep.js
: >.DS_Store
"${git_bin}" add .gitignore src/keep.ts packages/app/src.ts packages/mixed/keep.ts
"${git_bin}" -c commit.gpgsign=false commit -qm "feat: primary"
"${git_bin}" worktree add -q -b ci-tooling "${scratch}/ci"
"${git_bin}" -C "${scratch}/ci" rm -q .gitignore
"${git_bin}" -C "${scratch}/ci" -c commit.gpgsign=false commit -qm "chore: drop the ignore rules"
"${git_bin}" worktree add -q -b norm-keep "${scratch}/norm"

(cd "${scratch}/ci" && wt step copy-ignored) >/dev/null || fail "wt step copy-ignored failed"
before="$(count_untracked "${scratch}/ci")"
[[ "${before}" -eq 3 ]] || fail "the copied output must show as non-ignored untracked (got ${before})"

(cd "${scratch}/ci" && dev-profile-worktree-copy) >/dev/null || fail "dev-profile-worktree-copy failed"
after="$(count_untracked "${scratch}/ci")"
[[ "${after}" -eq 0 ]] || fail "the copied output must be excluded (got ${after} untracked)"

ci_git_dir="$("${git_bin}" -C "${scratch}/ci" rev-parse --path-format=absolute --git-dir)"
excludes="${ci_git_dir}/info/copy-ignored-excludes"
[[ -f "${excludes}" ]] || fail "no excludes file at ${excludes}"
value="$("${git_bin}" -C "${scratch}/ci" config --worktree core.excludesFile)"
[[ "${value}" == "${excludes}" ]] || fail "worktree core.excludesFile is [${value}]"
[[ "$("${git_bin}" -C "${scratch}/ci" config extensions.worktreeConfig)" == true ]] || fail "extensions.worktreeConfig is not enabled"
for rule in '.DS_Store' 'node_modules/' '/target/' '/packages/app/dist/' '/packages/mixed/junk.o'; do
	grep -qxF -- "${rule}" "${excludes}" || fail "the excludes file must list ${rule}"
done
if grep -qxF -- '/node_modules/' "${excludes}"; then
	fail "output the global ignore already covers must not be re-listed"
fi
"${git_bin}" -C "${scratch}/ci" check-ignore -q .DS_Store || fail "the folded global rules must keep .DS_Store ignored"

# The primary keeps its own rules and gets none of this.
printf 'untracked\n' >"${primary}/src/visible.ts"
[[ -n "$("${git_bin}" -C "${primary}" ls-files --others --exclude-standard)" ]] || fail "the primary's untracked visibility changed"
"${git_bin}" -C "${primary}" check-ignore -q target/build.o || fail "the primary's ignore rules changed"
(cd "${primary}" && dev-profile-worktree-copy) >/dev/null || fail "dev-profile-worktree-copy failed in the primary"
[[ ! -e "${primary}/.git/info/copy-ignored-excludes" ]] || fail "the primary context must not write an excludes file"

# A branch whose own tree covers the copied output gets no worktree key.
(cd "${scratch}/norm" && wt step copy-ignored) >/dev/null || fail "wt step copy-ignored failed for norm"
(cd "${scratch}/norm" && dev-profile-worktree-copy) >/dev/null || fail "dev-profile-worktree-copy failed for norm"
[[ "$(count_untracked "${scratch}/norm")" -eq 0 ]] || fail "norm must stay clean through its own rules"
norm_git_dir="$("${git_bin}" -C "${scratch}/norm" rev-parse --path-format=absolute --git-dir)"
[[ ! -e "${norm_git_dir}/info/copy-ignored-excludes" ]] || fail "a covered branch must not get a worktree excludesFile"

# Re-runs rewrite nothing, and newly copied output appends without dropping
# the rules already written.
cp "${excludes}" "${scratch}/excludes-once"
(cd "${scratch}/ci" && dev-profile-worktree-copy) >/dev/null || fail "dev-profile-worktree-copy re-run failed"
cmp -s "${excludes}" "${scratch}/excludes-once" || fail "a re-run must not rewrite the excludes file"
mkdir -p "${primary}/newout"
printf 'built\n' >"${primary}/newout/build2.o"
printf 'newout/\n' >>"${primary}/.gitignore"
(cd "${scratch}/ci" && wt step copy-ignored) >/dev/null || fail "wt step copy-ignored failed after new output"
(cd "${scratch}/ci" && dev-profile-worktree-copy) >/dev/null || fail "dev-profile-worktree-copy failed after new output"
grep -qxF -- '/newout/' "${excludes}" || fail "newly copied output must be appended"
grep -qxF -- '/target/' "${excludes}" || fail "the append must keep the earlier rules"
[[ "$(count_untracked "${scratch}/ci")" -eq 0 ]] || fail "ci untracked after the append"

echo "ok worktree-copy-excludes"
