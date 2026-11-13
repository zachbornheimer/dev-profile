#!/usr/bin/env bash
# The owners this profile treats as its own come from one file, so a profile built on this one
# swaps the list without editing a script: dev-profile-owners, dev-profile-repo-owned and the
# trust step in dev-profile-enter all follow DEV_PROFILE_OWNERS.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL owners: $*" >&2
	exit 1
}

owners="${repo}/bin/dev-profile-owners"
owned="${repo}/bin/dev-profile-repo-owned"
unset DEV_PROFILE_REPO_OWNED
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export PATH="${repo}/bin:${PATH}"

# 1. The shipped list names the author's accounts, case-insensitively.
"${owners}" zachbornheimer || fail "zachbornheimer is not in config/owners"
"${owners}" Software-Automation-Holdings-LLC || fail "owner lookup must ignore case"
if "${owners}" can1357; then fail "can1357 must not be an owner"; fi
if "${owners}" zachbornheimer-evil; then fail "owner lookup must match the whole login"; fi

# 2. A replacement list wins: only its logins are owned, comments and blanks are ignored.
printf '%s\n' '# an adopter' 'Acme' '' 'acme-labs # trailing comment' >"${scratch}/owners"
export DEV_PROFILE_OWNERS="${scratch}/owners"
"${owners}" acme || fail "an adopter's owner must be recognized"
"${owners}" ACME-LABS || fail "a trailing comment must not leak into the login"
if "${owners}" zachbornheimer; then fail "the shipped list must not apply under an override"; fi
[[ "$("${owners}")" == $'acme\nacme-labs' ]] || fail "listing must print the normalized logins"

# 3. dev-profile-repo-owned follows the override.
git init -q -b main "${scratch}/acme"
git -C "${scratch}/acme" remote add origin "https://github.com/acme/tool.git"
(cd "${scratch}/acme" && "${owned}") || fail "an acme repo must be owned under the acme list"
git init -q -b main "${scratch}/mine"
git -C "${scratch}/mine" remote add origin "git@github.com:zachbornheimer/tool.git"
if (cd "${scratch}/mine" && "${owned}"); then
	fail "a zachbornheimer repo must be unowned once the list is replaced"
fi

# 4. A missing list is an error, never an empty allow-list that silently owns nothing.
export DEV_PROFILE_OWNERS="${scratch}/absent"
if "${owners}" acme 2>/dev/null; then fail "a missing owners file must not answer"; fi
[[ "$("${owners}" acme >/dev/null 2>&1 || echo $?)" == 2 ]] || fail "a missing owners file must exit 2"

echo "ok"
