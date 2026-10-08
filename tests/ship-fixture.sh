#!/usr/bin/env bash
# `wt ship` publishes nothing for a branch with no commits ahead of its base,
# and publishes one that is ahead. Real git; gh and wt are stubs.
# Usage: ship-fixture.sh <generated-dir>
set -euo pipefail
export HK=0 # no global git hooks inside the fixture repo

out="${1:?usage: ship-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL ship fixture: $*" >&2
	exit 1
}

stubs="${work}/stubs"
mkdir -p "$stubs"
# gh: repo facts answer; "pr create" is the publish we must (not) reach.
cat >"${stubs}/gh" <<'STUB'
#!/usr/bin/env bash
case "$*" in
*defaultBranchRef*) echo main ;;
*owner*) echo me ;;
"pr create"*) echo "gh pr create" >>"${SHIP_LOG}" ;;
esac
STUB
cat >"${stubs}/wt" <<'STUB'
#!/usr/bin/env bash
[[ "$1 $2" == "list --full" ]] && echo '{"items":[]}'
exit 0
STUB
chmod +x "${stubs}/gh" "${stubs}/wt"

git init -q --bare "${work}/origin.git"
git clone -q "${work}/origin.git" "${work}/repo" 2>/dev/null
cd "${work}/repo"
git config user.email t@example.com
git config user.name t
git switch -q -c main
git commit -q --allow-empty -m base
git push -q origin main
git switch -q -c feature

# Extract the rendered alias before the stub wt shadows the real one.
script="${work}/ship.sh"
wt --config "${out}/worktrunk.toml" config alias show ship | sed '1d; s/^  //' >"$script"
export SHIP_LOG="${work}/log" PATH="${stubs}:${PATH}"
: >"$SHIP_LOG"

bash "$script" >/dev/null 2>&1 || fail "branch equal to base must exit 0"
[[ ! -s "$SHIP_LOG" ]] || fail "branch equal to base must not create a PR"

git commit -q --allow-empty -m change
bash "$script" >/dev/null 2>&1 || fail "branch ahead of base must ship"
grep -q "gh pr create" "$SHIP_LOG" || fail "branch ahead of base must create a PR"
echo "ship fixture ok"
