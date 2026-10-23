#!/usr/bin/env bash
# conform.lua resolves dprint's real binary with `mise which` once per directory,
# and drops the answer when the binary is gone or the mise config changes.
# A fake `mise` counts its calls; nvim loads the real conform.lua headless.
set -euo pipefail
fail() {
	echo "FAIL conform-resolve fixture: $*" >&2
	exit 1
}

nvim_bin=$(command -v nvim) || {
	echo "conform-resolve fixture skipped: nvim not installed"
	exit 0
}
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
work=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/bin" "$work/out" "$work/proj" "$work/data/shims"
: >"$work/out/mise-profile.toml"
printf '{"filetypes":{}}\n' >"$work/out/profile.json"
for v in 1 2 3 4; do
	printf '#!/bin/sh\n' >"$work/dprint-$v"
	chmod +x "$work/dprint-$v"
done
printf '#!/bin/sh\n' >"$work/data/shims/dprint"
chmod +x "$work/data/shims/dprint"

# `mise which dprint`: prints $FAKE_DPRINT, counts calls, fails when FAKE_FAIL is set.
cat >"$work/bin/mise" <<'EOF'
#!/bin/sh
echo call >>"$FAKE_COUNT"
[ -z "${FAKE_FAIL:-}" ] || exit 1
echo "$FAKE_DPRINT"
EOF
chmod +x "$work/bin/mise"

cat >"$work/check.lua" <<'EOF'
local work = os.getenv("WORK")
package.loaded["conform.util"] = {
  root_file = function()
    return function()
      return nil
    end
  end,
}
local command = dofile(os.getenv("CONFORM_LUA")).opts.formatters.dprint.command
local ctx = { filename = work .. "/proj/a.md" }

local function calls()
  local n = 0
  for _ in io.lines(work .. "/count") do
    n = n + 1
  end
  return n
end
local function expect(label, got, want)
  if got ~= want then
    io.stderr:write(string.format("FAIL conform-resolve fixture: %s: got %s, want %s\n", label, tostring(got), tostring(want)))
    os.exit(1)
  end
end
local function using(n)
  vim.uv.os_setenv("FAKE_DPRINT", work .. "/dprint-" .. n)
end

using(1)
expect("first save resolves", command({}, ctx), work .. "/dprint-1")
expect("first save asks mise once", calls(), 1)
expect("second save uses the cache", command({}, ctx), work .. "/dprint-1")
expect("second save does not ask mise", calls(), 1)

os.remove(work .. "/dprint-1")
using(2)
expect("a removed binary is re-resolved", command({}, ctx), work .. "/dprint-2")
expect("re-resolve asks mise again", calls(), 2)

using(3)
local profile = io.open(work .. "/out/mise-profile.toml", "w")
profile:write("dprint = '0.64.4'\n")
profile:close()
expect("a changed profile is re-resolved", command({}, ctx), work .. "/dprint-3")

using(4)
local project = io.open(work .. "/proj/mise.toml", "w")
project:write("[tools]\n")
project:close()
expect("a new project config is re-resolved", command({}, ctx), work .. "/dprint-4")
expect("each change asked mise once", calls(), 4)

vim.uv.os_setenv("FAKE_FAIL", "1")
os.remove(work .. "/dprint-4")
expect("a failing mise falls back to the shim", command({}, ctx), work .. "/data/shims/dprint")
EOF

: >"$work/count"
WORK="$work" CONFORM_LUA="${CONFORM_LUA:-$root/conform.lua}" DEV_PROFILE_OUT="$work/out" MISE_DATA_DIR="$work/data" \
	FAKE_COUNT="$work/count" PATH="$work/bin:/usr/bin:/bin" \
	"$nvim_bin" --headless --clean -l "$work/check.lua" || fail "nvim run (see above)"
echo "conform-resolve fixture ok"
