#!/usr/bin/env bash
# The doctor warning for kernel and runtime pins: a stubbed `mise ls` stands in
# for the machine; the warning names each drifted tool and still exits 0.
# Usage: kernel-pins-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: kernel-pins-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
warner="${out}/bin/dev-profile-kernel-pins"

fail() {
	echo "FAIL kernel-pins fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

# The stub prints $MISE_LS_JSON for `mise ls --global --json`.
mkdir -p "${work}/bin"
cat >"${work}/bin/mise" <<'STUB'
#!/usr/bin/env bash
[[ "$*" == "ls --global --json" ]] || exit 1
printf '%s' "${MISE_LS_JSON}"
STUB
chmod +x "${work}/bin/mise"

# One entry per pinned tool, installed at its pin plus a patch suffix for prefix pins.
all_current() {
	jq -Rn '[inputs | split(" ") | {key: .[0], value: [{version: (.[1] + (if (.[1] | test("^[0-9]+\\.[0-9]+\\.[0-9]+")) then "" else ".1" end)), installed: true, active: true}]}] | from_entries' \
		< <(awk '/^\[/ { in_tools = ($0 == "[tools]"); next } in_tools && /=/' "${out}/mise-profile.toml" |
			sed -E 's/^"?([^"=]+[^"= ])"? *= *"(.*)"$/\1 \2/')
}

run_warner() { # <mise ls json>: must exit 0
	MISE_LS_JSON="$1" PATH="${work}/bin:${PATH}" "$warner" >"${work}/output.txt" 2>&1 || fail "the warning must exit 0"
}

run_warner "$(all_current)"
[[ ! -s "${work}/output.txt" ]] || fail "machine matches the profile: no warning expected"

pkl_pin="$(sed -n 's/^pkl = "\(.*\)"$/\1/p' "${out}/mise-profile.toml")"
[[ -n "$pkl_pin" ]] || fail "the rendered profile has no pkl pin"
run_warner "$(all_current | jq '.pkl[0].version = "0.0.1"')"
grep -Fq "doctor: pkl ${pkl_pin} is pinned by the profile but is not the active installed version" "${work}/output.txt" ||
	fail "a drifted pkl must warn"
[[ "$(wc -l <"${work}/output.txt")" -eq 1 ]] || fail "only the drifted tool must warn"

run_warner "$(all_current | jq 'del(.pkl)')"
grep -Fq "doctor: pkl" "${work}/output.txt" || fail "an absent pkl must warn"

run_warner '{}'
grep -Fq "doctor: pkl" "${work}/output.txt" || fail "an empty machine must warn"

echo "kernel-pins fixture ok"
