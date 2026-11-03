#!/usr/bin/env bash
# The workflow gates ratchet: dev-profile-lint-ratchet (actionlint, yamllint,
# zizmor) and dev-profile-pinact-ratchet block only the findings a change
# introduces. Debt the file already carried at its merge base with origin's
# default branch passes; a finding the change itself adds still blocks.
set -euo pipefail
for tool in actionlint yamllint zizmor pinact; do
	command -v "${tool}" >/dev/null 2>&1 || exit 0
done

src="$(cd "$(dirname "$0")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
fail() {
	echo "FAIL lint-ratchet fixture: $*" >&2
	exit 1
}
export GIT_CONFIG_GLOBAL="$work/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "$GIT_CONFIG_GLOBAL" user.name fixture
git config --file "$GIT_CONFIG_GLOBAL" user.email fixture@example.invalid
git config --file "$GIT_CONFIG_GLOBAL" commit.gpgsign false

repo="$work/repo"
git init -q -b main "$repo"
cd "$repo"
mkdir -p .github/workflows
# Upstream already carries one finding of every class the gate judges: an
# unquoted expansion, a pin comment naming the wrong tag, a trailing space.
cat >.github/workflows/carried.yml <<'YML'
name: carried
on: push
jobs:
  carried:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo $INHERITED
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6
YML
printf 'name: spaced\non: push\njobs:\n  spaced:\n    runs-on: ubuntu-latest\n    steps:\n     - run: "true" \n' >.github/workflows/spaced.yml
git add -A
git commit -q -m upstream
git update-ref refs/remotes/origin/main HEAD
git switch -q -c feature

al() { "$src/bin/dev-profile-lint-ratchet" actionlint -- "$@" >"$work/out" 2>&1; }
yl() { "$src/bin/dev-profile-lint-ratchet" yamllint --strict -- "$@" >"$work/out" 2>&1; }
zz() { "$src/bin/dev-profile-lint-ratchet" zizmor -- "$@" >"$work/out" 2>&1; }
pa() { "$src/bin/dev-profile-pinact-ratchet" "$@" >"$work/out" 2>&1; }

# An edit elsewhere in the file keeps every inherited finding and adds none.
printf '\n# touched\n' >>.github/workflows/carried.yml
for gate in al yl pa; do
	"${gate}" .github/workflows/carried.yml || fail "inherited findings must not block ${gate}: $(cat "$work/out")"
done
yl .github/workflows/spaced.yml || fail "inherited trailing space must not block yamllint: $(cat "$work/out")"

# One new finding per tool, each introduced by this change, still blocks.
cat >.github/workflows/introduced.yml <<'YML'
name: introduced
on: push
jobs:
  introduced:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo $INTRODUCED
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.1.0
YML
printf 'name: spaced2\non: push\njobs:\n  spaced2:\n    runs-on: ubuntu-latest\n    steps:\n     - run: "true" \n' >.github/workflows/spaced2.yml
cat >.github/workflows/inherit.yml <<'YML'
name: inherit
on: push
jobs:
  inherit:
    uses: ./.github/workflows/child.yml
    secrets: inherit
YML
printf 'name: child\non: workflow_call\njobs:\n  child:\n    runs-on: ubuntu-latest\n    steps:\n      - run: "true"\n' >.github/workflows/child.yml
git add -A
git commit -q -m "feat: introduce findings"

if al .github/workflows/introduced.yml; then fail "an introduced unquoted expansion must block actionlint"; fi
grep -q 'SC2086' "$work/out" || fail "actionlint must print the introduced rule: $(cat "$work/out")"
if yl .github/workflows/spaced2.yml; then fail "an introduced trailing space must block yamllint"; fi
if zz .github/workflows/inherit.yml; then fail "an introduced secrets: inherit must block zizmor"; fi
grep -q 'secrets-inherit' "$work/out" || fail "zizmor must print the introduced rule: $(cat "$work/out")"
if pa .github/workflows/introduced.yml; then fail "an introduced pin-comment mismatch must block pinact"; fi
grep -q 'v6\.1\.0' "$work/out" || fail "pinact must print the introduced mismatch: $(cat "$work/out")"

echo "ok lint-ratchet fixture"
