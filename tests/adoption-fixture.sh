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

check_review_config() {
	python3 - "${1:-${HOME}/.opencodereview/config.json}" <<'PY'
import json, os, pathlib, subprocess, sys

if not __debug__:
    raise SystemExit("adoption checks require assertions; unset PYTHONOPTIMIZE")

path = pathlib.Path(sys.argv[1])
config = json.loads(path.read_text())
assert set(config) == {"llm"}
llm = config["llm"]
assert llm["model"] == "deepseek/deepseek-v4.1-flash"
assert llm["protocol"] == "openai"
assert llm["url"] == "http://mcp-gateway.tail158749.ts.net:4000/v1"
assert set(llm) == {"url", "protocol", "model", "auth_token_cmd"}
# Resolve a synthetic credential at use, never from a stored JSON token.
env = dict(os.environ, AUTH_GATEWAY_TOKEN="adoption-fixture-credential")
assert llm["auth_token_cmd"] == 'printf %s "${AUTH_GATEWAY_TOKEN:?AUTH_GATEWAY_TOKEN is not set or empty}"'
result = subprocess.run(["sh", "-c", llm["auth_token_cmd"]], env=env, capture_output=True, text=True, check=True)
assert result.stdout == env["AUTH_GATEWAY_TOKEN"]
for state in ("absent", "empty"):
    missing_env = dict(os.environ)
    missing_env.pop("AUTH_GATEWAY_TOKEN", None)
    if state == "empty":
        missing_env["AUTH_GATEWAY_TOKEN"] = ""
    result = subprocess.run(["sh", "-c", llm["auth_token_cmd"]], env=missing_env, capture_output=True, text=True)
    assert result.returncode != 0, f"{state} AUTH_GATEWAY_TOKEN must fail"
    assert result.stdout == "", f"{state} token must not produce a credential"
    assert "AUTH_GATEWAY_TOKEN is not set or empty" in result.stderr, result.stderr
PY
}
# 1. The seed deploys from the clone wherever it lives. Only the first apply needs the root named.
MISE_DOTFILES_ROOT="${clone}" mise dot apply --yes || fail "initial apply failed"
for target in .opencodereview/config.json .config/hk/config.pkl .omp/agent/extensions/handler-timing.ts .omp/agent/extensions/extension-timeout-repair.ts .config/dprint/dprint.jsonc .local/share/dev-profile/bin .stylelintrc.json .omp/agent/extensions/agent-checkpoint-publish.ts .config/agent-checkpoints/enrollment.toml; do
	[ -L "${HOME}/${target}" ] || fail "${target} was not linked"
	case "$(realpath "${HOME}/${target}")" in
	"${clone}"/*) ;;
	*) fail "${target} resolves outside the clone: $(realpath "${HOME}/${target}")" ;;
	esac
	# A link that resolves only through a machine-specific home (/Users/<name>) dangles on every other machine.
	[ -e "${HOME}/${target}" ] || fail "${target} dangles"
	case "$(readlink "${HOME}/${target}")" in
	"${scratch}"/*) ;;
	*) fail "${target} links through a path outside the scratch home: $(readlink "${HOME}/${target}")" ;;
	esac
done

check_review_config

# The fixture must validate its command literal before executing config content.
python3 - "${HOME}/.opencodereview/config.json" "${scratch}" <<'PY'
import json, pathlib, shlex, sys

config = json.loads(pathlib.Path(sys.argv[1]).read_text())
scratch = pathlib.Path(sys.argv[2])
config["llm"]["auth_token_cmd"] = "touch " + shlex.quote(str(scratch / "command-ran"))
(scratch / "unsafe-review.json").write_text(json.dumps(config))
PY
if check_review_config "${scratch}/unsafe-review.json" >"${scratch}/unsafe-review.log" 2>&1; then
	fail "unexpected auth_token_cmd was accepted"
fi
[ ! -e "${scratch}/command-ran" ] || fail "unexpected auth_token_cmd ran before validation"
grep -q AssertionError "${scratch}/unsafe-review.log" || fail "unexpected command was not rejected by the contract"

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

mise dot apply --yes >/dev/null 2>&1 || fail "repeat apply failed without MISE_DOTFILES_ROOT"
check_review_config

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
