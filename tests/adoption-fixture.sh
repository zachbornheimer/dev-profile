#!/usr/bin/env bash
# Prove the profile is adoptable: a clone at an arbitrary path (spaces included) deploys through
# the seeded global config using only dotfiles.root, the root then follows the linked fragment
# with no environment variable, nothing personal deploys by default, and the personal code-root
# targets arrive only once config/personal.toml is linked into conf.d.
# Runs the real mise against a scratch HOME; the live HOME and ~/.config/mise are never touched.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
live_home="$HOME"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL adoption: $*" >&2
	exit 1
}

clone="${scratch}/an arbitrary clone"
mkdir -p "${clone}"
(cd "${root}" && git ls-files -z --cached --others --exclude-standard | tar --null -T - -cf -) | tar -xf - -C "${clone}"

export HOME="${scratch}/home"
export XDG_CONFIG_HOME="${HOME}/.config"
export MISE_GLOBAL_CONFIG_FILE="${HOME}/.config/mise/config.toml"
export MISE_STATE_DIR="${scratch}/state" MISE_DATA_DIR="${scratch}/data" MISE_CACHE_DIR="${scratch}/cache"
export MISE_OFFLINE=true MISE_AUTO_INSTALL=false MISE_TRUSTED_CONFIG_PATHS="${scratch}"
unset MISE_DOTFILES_ROOT MISE_ENV
[ "${HOME}" != "${live_home}" ] || fail "scratch HOME is the live HOME"

mkdir -p "${HOME}/.config/mise"
cp "${clone}/config/mise.toml" "${MISE_GLOBAL_CONFIG_FILE}"
cd "${HOME}"

# 1. The seed deploys from the clone wherever it lives. Only the first apply needs the root named.
applied="$(MISE_DOTFILES_ROOT="${clone}" mise dot apply --yes 2>&1 | grep -v 'WARN' || true)"
for target in .agents .config/hk/config.pkl .config/dprint/dprint.jsonc .local/share/dev-profile/bin .stylelintrc.json; do
	[ -L "${HOME}/${target}" ] || fail "${target} was not linked. apply said: ${applied}"
	case "$(realpath "${HOME}/${target}")" in
	"${clone}"/*) ;;
	*) fail "${target} resolves outside the clone: $(realpath "${HOME}/${target}")" ;;
	esac
done

# 2. The seed names no machine path in any source.
if grep -nE 'source = "(~|/)' "${clone}/config/mise.toml" >&2; then
	fail "config/mise.toml still declares an absolute source"
fi

# 3. The group deploys its entries and nothing else of the clone.
for stray in README.md LICENSE mise.toml tests bin; do
	[ ! -e "${HOME}/${stray}" ] || fail "${stray} leaked into HOME"
done

# 4. After the first apply the fragment carries the root: no environment variable needed.
[ "$(mise settings get dotfiles.root)" = "${clone}" ] ||
	fail "dotfiles.root is $(mise settings get dotfiles.root), not the clone ${clone}"
mise dot status --json 2>/dev/null | grep -Eq '"state": "(missing|differs|source_missing)"' &&
	fail "an entry is not applied when the root comes from the fragment"

# 5. The personal code-root targets are absent until the overlay is linked.
[ ! -e "${HOME}/Developer" ] || fail "personal targets deployed without the personal overlay"
ln -s "${clone}/config/personal.toml" "${HOME}/.config/mise/conf.d/personal.toml"
mise dot apply --yes >/dev/null 2>&1 || fail "apply failed with the personal overlay linked"
for target in .editorconfig .golangci.yml deny.toml dprint.jsonc mise.toml; do
	[ -L "${HOME}/Developer/Personal/${target}" ] || fail "Developer/Personal/${target} missing after linking the personal overlay"
done
[ "$(realpath "${HOME}/Developer/Personal/mise.toml")" = "${clone}/config/personal-overlay.toml" ] ||
	fail "Developer/Personal/mise.toml does not point at config/personal-overlay.toml"
mise dot status --json 2>/dev/null | grep -Eq '"state": "(missing|differs|source_missing)"' &&
	fail "an entry is not applied after the personal overlay"

echo "ok"
