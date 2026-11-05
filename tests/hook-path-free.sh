#!/usr/bin/env bash
# Git runs the global hk hooks from whatever process pushed: an agent, launchd, cron.
# None of those has the profile bin directory on PATH (only a login shell does), so a
# hk step that calls a dev-profile-* helper by bare name dies with "command not found"
# (exit 127). Push through the repo's home/gitconfig hooks with a PATH reduced to the
# system dirs plus git, and require the dev-profile-* steps to run and pass.
#
# That PATH is a deployed machine's: mise at ~/.local/bin, the helpers at
# ~/.local/share/dev-profile/bin. Build both in a scratch HOME so a checkout that was
# never deployed (CI) runs this fixture too. The one thing the scratch HOME does not
# own is hk's package cache, which stays with the machine: sharing it is what keeps
# this fixture from re-fetching hk's release zip on every run.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gitconfig="${repo}/home/gitconfig"
live_home="$HOME"
# The machine's data directory: the hook's `mise x hk` runs the hk it has installed
# instead of downloading one into the scratch HOME.
mise_data_dir="${MISE_DATA_DIR:-${live_home}/.local/share/mise}"
scratch="$(mktemp -d)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL hook-path-free: $*" >&2
	[[ ! -f "${scratch}/push.txt" ]] || sed 's/^/  | /' "${scratch}/push.txt" >&2
	exit 1
}

mise_bin="$(command -v mise)" || fail "mise is not on PATH"
export HOME="${scratch}/home"
mkdir -p "${HOME}/.local/bin" "${HOME}/.local/share/dev-profile"
ln -s "${repo}/bin" "${HOME}/.local/share/dev-profile/bin"
ln -s "$(readlink -f "${mise_bin}")" "${HOME}/.local/bin/mise"

# Config-based hooks need git >= 2.36; the system git (2.50) on macOS ignores them.
# Take mise's pinned git when it manages one (Linux), else the PATH's (Homebrew on
# macOS), and follow the symlink so the restricted PATH below holds no other wrapper.
git_bin="$(readlink -f "$(mise which git 2>/dev/null || command -v git)")"
git_dir="$(dirname "${git_bin}")"
hk_config="${scratch}/hk-config"
mkdir -p "${hk_config}"
# Only the dev-profile-* steps: this fixture judges how the hook finds its helpers, not
# which steps the full profile runs.
# The package is the one the profile pins, so it is the one already in the shared cache
# below: doctor validates hk/hk.pkl (same URI) before this fixture, and hk caches the zip
# by URL. Pinning a version the profile does not use made every run fetch a second copy.
hk_version="$(sed -n 's|.*github.com/jdx/hk/releases/download/v\([0-9][.0-9]*\)/hk@.*|\1|p' "${repo}/hk/hk.pkl" | head -1)"
[[ -n "${hk_version}" ]] || fail "no hk package URI in ${repo}/hk/hk.pkl"
cat >"${hk_config}/config.pkl" <<PKL
amends "package://github.com/jdx/hk/releases/download/v${hk_version}/hk@${hk_version}#/Config.pkl"
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

# env -i: nothing of this shell's PATH, mise shims or profile reaches the hook. The data
# directory crosses so `mise x hk` finds the installed hk; the package cache crosses so the
# hook reuses the hk release package the machine already fetched instead of downloading it
# into the scratch HOME (a 504 on that fetch failed the whole test job).
mkdir -p "${live_home}/.pkl/cache"
status=0
env -i HOME="${HOME}" PATH="${bare_path}" MISE_DATA_DIR="${mise_data_dir}" \
	HK_PKL_CACHE_DIR="${live_home}/.pkl/cache" \
	GIT_CONFIG_GLOBAL="${gitconfig}" HK_CONFIG_DIR="${hk_config}" \
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
