#!/usr/bin/env bash
# The plugin identifier belongs in the key, while its version is an explicit field.
# Optional argument checks a live mise config without modifying it.
set -euo pipefail
command -v betterleaks >/dev/null
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
scan() {
	printf '%s\n' "$1" | betterleaks stdin --redact --no-banner >"$scratch/scan.log" 2>&1
}
scalar='[tools]
"vfox:jdx/vfox-1password" = "2.42.0"'
explicit='[tools]
"vfox:jdx/vfox-1password" = { version = "2.42.0" }'
if scan "$scalar"; then
	echo 'FAIL: scalar reproduction no longer triggers scanner; reassess construction' >&2
	exit 1
fi
scan "$explicit"
if scan "$explicit
[env]
password = \"fixture-password-7tY8uI9oP0aS1dF2\""; then
	echo 'FAIL: password finding was suppressed' >&2
	exit 1
fi
python3 - "${1:-}" <<'PY'
import pathlib
import sys
import tomllib
key = 'vfox:jdx/vfox-1password'
scalar = '[tools]\n"vfox:jdx/vfox-1password" = "2.42.0"'
explicit = '[tools]\n"vfox:jdx/vfox-1password" = { version = "2.42.0" }'
assert tomllib.loads(scalar)['tools'][key] == tomllib.loads(explicit)['tools'][key]['version']
if sys.argv[1]:
    config = tomllib.loads(pathlib.Path(sys.argv[1]).read_text())
    tool = config['tools'][key]
    assert isinstance(tool, dict), 'plugin version must use an explicit version field'
    assert tool['version'] == '2.42.0', 'version changed during declaration rewrite'
PY
printf 'ok version-pin: explicit version scans clean; password rejected; TOML version unchanged\n'
