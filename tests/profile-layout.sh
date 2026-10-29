#!/usr/bin/env bash
# Prove the fragment folder: ~/.config/mise/conf.d/dev-profile links the checkout's profile/,
# and every pin declared in languages/<lang>/tools.toml reaches the merged global config
# through its `include`. The [settings] that mise refuses inside an include must still apply,
# which is why they stay in profile/mise.toml.
# Runs in a scratch HOME; the live HOME and ~/.config/mise are never touched.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
live_home="$HOME"
scratch="$(mktemp -d)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL profile layout: $*" >&2
	exit 1
}

export HOME="${scratch}/home"
export XDG_CONFIG_HOME="${HOME}/.config"
export XDG_STATE_HOME="${HOME}/.local/state"
export XDG_CACHE_HOME="${HOME}/.cache"
export MISE_DATA_DIR="${scratch}/mise-data"
export MISE_STATE_DIR="${scratch}/mise-state"
export MISE_CACHE_DIR="${scratch}/mise-cache"
unset MISE_GLOBAL_CONFIG_FILE MISE_TRUSTED_CONFIG_PATHS

[ "${HOME}" != "${live_home}" ] || fail "scratch HOME is the live HOME"

# 1. The split is complete: the pins are one file per language, and the single-file
#    fragment they came from is gone.
[ -f "${root}/profile/mise.toml" ] || fail "profile/mise.toml is missing"
[ ! -e "${root}/config/tools.toml" ] || fail "config/tools.toml still exists; the pins belong in languages/<lang>/tools.toml"
for lang in common agents docker go kubernetes node python ruby rust terraform; do
	[ -f "${root}/languages/${lang}/tools.toml" ] || fail "languages/${lang}/tools.toml is missing"
done

# 2. The folder fragment loads: mise reads profile/mise.toml from the conf.d link.
mkdir -p "${HOME}/.config/mise/conf.d"
ln -s "${root}/profile" "${HOME}/.config/mise/conf.d/dev-profile"
cd "${HOME}"

listed="$(mise config ls)" || fail "mise config ls exited nonzero"
[ "$(wc -l <<<"${listed}" | tr -d ' ')" = "1" ] || fail "expected one global config file, got: ${listed}"
case "${listed}" in
*conf.d/dev-profile/mise.toml*) ;;
*) fail "the loaded config is not the fragment's mise.toml: ${listed}" ;;
esac

# 3. Every declared pin reached the merge.
merged="$(mise config ls -J)" || fail "mise config ls -J exited nonzero"
declared="$(awk '/^[[:space:]]*#/ {next} /=/ {sub(/=.*/, ""); gsub(/[[:space:]"]/, ""); print}' "${root}"/languages/*/tools.toml | sort -u)"
[ -n "${declared}" ] || fail "no pins found in languages/*/tools.toml"
missing=""
while IFS= read -r pin; do
	grep -Fq "\"${pin}\"" <<<"${merged}" || missing="${missing} ${pin}"
done <<<"${declared}"
[ -z "${missing}" ] || fail "pins declared but not merged:${missing}"

# 4. [settings] from the entry applies, so nobody moved it into an include (mise rejects that).
[ "$(mise settings get auto_install)" = "true" ] || fail "auto_install is not true"
[ "$(mise settings get experimental)" = "true" ] || fail "experimental is not true"
mise settings get trusted_config_paths | grep -Fq '~/Developer' || fail "trusted_config_paths lost the code root"

echo "ok"
