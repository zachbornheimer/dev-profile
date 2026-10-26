#!/usr/bin/env bash
# Git runs the global hk hooks from whatever process pushed: an agent, launchd, cron.
# None of those has the profile bin directory on PATH (only a login shell does), so a
# hk step that calls a dev-profile-* helper by bare name dies with "command not found"
# (exit 127). Push through the repo's home/gitconfig hooks with a PATH reduced to the
# system dirs plus git, and require the dev-profile-* steps to run and pass.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gitconfig="${repo}/home/gitconfig"
bin_dir="${HOME}/.local/share/dev-profile/bin"
scratch="$(mktemp -d)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL hook-path-free: $*" >&2
	[[ ! -f "${scratch}/push.txt" ]] || sed 's/^/  | /' "${scratch}/push.txt" >&2
	exit 1
}

[[ -d "${bin_dir}" ]] || fail "${bin_dir} is not installed; run: mise dot apply"

# Config-based hooks need the profile's pinned git; the system git (2.50) ignores them.
git_bin="$(mise which git)"
git_dir="$(dirname "${git_bin}")"
hk_config="${scratch}/hk-config"
mkdir -p "${hk_config}"
# Only the dev-profile-* steps: this fixture judges how the hook finds its helpers, not
# which steps the full profile runs.
cat >"${hk_config}/config.pkl" <<'PKL'
amends "package://github.com/jdx/hk/releases/download/v2.5.0/hk@2.5.0#/Config.pkl"
hooks {
  ["pre-push"] {
    steps {
      ["identity-guard"] { check = "dev-profile-identity-guard" }
      ["no-trunk-prettier"] { check = "dev-profile-ban-trunk-prettier" }
      ["suppressions"] { check = "dev-profile-suppressions --unpushed" }
      ["if-installed"] { check = "dev-profile-if-installed no-such-tool-fixture no-such-tool-fixture" }
    }
  }
}
PKL

author=(GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
	GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid)
bare_path="${git_dir}:/usr/bin:/bin"
git init -q --bare "${scratch}/remote.git"
git init -q -b feature "${scratch}/work"
echo hello >"${scratch}/work/a.txt"
git -C "${scratch}/work" add a.txt
env "${author[@]}" HK=0 "${git_bin}" -C "${scratch}/work" -c commit.gpgsign=false commit -qm "feat: fixture"
git -C "${scratch}/work" remote add origin "${scratch}/remote.git"

# env -i: nothing of this shell's PATH, mise shims or profile reaches the hook.
status=0
env -i HOME="${HOME}" PATH="${bare_path}" GIT_CONFIG_GLOBAL="${gitconfig}" HK_CONFIG_DIR="${hk_config}" \
	git -C "${scratch}/work" push -q origin feature >"${scratch}/push.txt" 2>&1 || status=$?

if grep -q 'command not found' "${scratch}/push.txt"; then
	fail "a hook step could not find its dev-profile helper"
fi
[[ "${status}" -eq 0 ]] || fail "push exited ${status}"
for step in identity-guard no-trunk-prettier suppressions if-installed; do
	grep -q "✔ ${step}" "${scratch}/push.txt" || fail "step ${step} did not run and pass"
done
# Every hk entry in the gitconfig, not just pre-push: each one starts hk the same way.
hooks="$(git config --file "${gitconfig}" --get-regexp '^hook\.hk-.*\.command$')"
[[ -n "${hooks}" ]] || fail "no hook.hk-*.command in ${gitconfig}"
while IFS= read -r line; do
	[[ "${line}" == *'${HOME}/.local/share/dev-profile/bin'* ]] ||
		fail "${line%% *} does not put the dev-profile bin directory on PATH"
done <<<"${hooks}"
echo "ok hook-path-free"
