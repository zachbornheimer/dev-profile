#!/usr/bin/env bash
# dev-profile-ruff-new blocks only ruff findings a change introduces: findings the
# file already had at its merge base with origin's default branch pass.
set -euo pipefail
command -v ruff >/dev/null 2>&1 || exit 0

src="$(cd "$(dirname "$0")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
fail() {
	echo "FAIL ruff-new fixture: $*" >&2
	exit 1
}
export GIT_CONFIG_GLOBAL="$work/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "$GIT_CONFIG_GLOBAL" user.name fixture
git config --file "$GIT_CONFIG_GLOBAL" user.email fixture@example.invalid
git config --file "$GIT_CONFIG_GLOBAL" commit.gpgsign false

repo="$work/repo"
git init -q -b main "$repo"
cd "$repo"
# Upstream's file already catches a blind exception (BLE001) and does nothing with it (S110).
printf 'def f():\n    try:\n        return 1\n    except Exception:\n        pass\n' >mod.py
git add mod.py
git commit -q -m upstream
git update-ref refs/remotes/origin/main HEAD
git switch -q -c feature

gate() { "$src/bin/dev-profile-ruff-new" mod.py >"$work/out" 2>&1; }

# An edit elsewhere in the file keeps the inherited findings and adds none.
printf 'def f():\n    try:\n        return 2\n    except Exception:\n        pass\n\n\nVALUE = 1\n' >mod.py
gate || fail "inherited findings must not block: $(cat "$work/out")"

# A second blind except is introduced by the change and blocks.
printf '\n\ndef g():\n    try:\n        return 3\n    except Exception:\n        pass\n' >>mod.py
if gate; then fail "an introduced finding must block"; fi
grep -q 'BLE001' "$work/out" || fail "the introduced finding must be printed: $(cat "$work/out")"
grep -q '2 finding(s) introduced' "$work/out" || fail "only the new findings count: $(cat "$work/out")"

echo "ok ruff-new fixture"
