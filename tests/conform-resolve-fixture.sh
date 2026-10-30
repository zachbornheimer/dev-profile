#!/usr/bin/env bash
# A Neovim save runs the profile's pinned dprint: not what a stale PATH holds, not
# mise on the save path, and a new pin reaches the next save of a running Neovim.
# One headless nvim loads the real conform.lua and the generated wrapper; the
# dprint builds are stubs that name themselves.
# Usage: conform-resolve-fixture.sh <generated-dir>
set -euo pipefail
out="${1:?usage: conform-resolve-fixture.sh <generated-dir>}"
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

pin="$(sed -n 's/^dprint = "\(.*\)"$/\1/p' "${out}/mise-profile.toml")"
[[ -n "${pin}" ]] || fail "the rendered profile has no dprint pin"

# A dprint that prints its name and logs `<name> <arguments>` to $DP_CALLS.
stub() { # <path> <name>
	mkdir -p "$(dirname "$1")"
	printf '#!/bin/sh\necho "%s $*" >>"${DP_CALLS:-/dev/null}"\necho %s\n' "$2" "$2" >"$1"
	chmod +x "$1"
}

mkdir -p "${work}/out/bin" "${work}/out/lib" "${work}/path"
cp "${out}/bin/dev-profile-dprint" "${work}/out/bin/"
cp "${out}/lib/facts.sh" "${work}/out/lib/" # the pin the wrapper runs
printf '{"filetypes":{}}\n' >"${work}/out/profile.json"
stub "${work}/data/installs/dprint/${pin}/dprint" pinned
stub "${work}/data/shims/dprint" shim
stub "${work}/path/dprint" path # first on PATH, like a versioned install dir from before a pin change
# A mise that works but leaves a mark: a save that runs it has the wrong design, even when the answer is right.
printf '#!/bin/sh\necho called >"%s/mise-called"\necho "%s"\n' "${work}" "${work}/data/installs/dprint/${pin}/dprint" >"${work}/path/mise"
chmod +x "${work}/path/mise"

cat >"${work}/check.lua" <<'EOF'
local work = os.getenv("WORK")
package.loaded["conform.util"] = {
  root_file = function()
    return function() end
  end,
}
local spec = dofile(os.getenv("CONFORM_LUA"))
local dprint = spec.opts.formatters.dprint.command

local function expect(label, got, want)
  if got ~= want then
    io.stderr:write(string.format("FAIL conform-resolve fixture: %s: got %s, want %s\n", label, vim.inspect(got), vim.inspect(want)))
    os.exit(1)
  end
end

-- What a save runs: dprint formatting stdin.
local function save()
  local result = vim.system({ dprint, "fmt", "--stdin", work .. "/a.md" }, { text = true, stdin = "" }):wait(5000)
  return vim.trim(result.stdout or "")
end

local function logged(line)
  return vim.iter(io.lines(work .. "/calls")):any(function(l)
    return l == line
  end)
end

expect("the save command is one fixed path", type(dprint), "string")
expect("a stale PATH does not pick the build", save(), "pinned")

expect("conform.lua warms the plugin cache at startup", type(spec.init), "function")
spec.init()
vim.api.nvim_exec_autocmds("VimEnter", { group = "dev_profile_dprint_warm" })
expect("startup warms the plugin cache through the pinned build", vim.wait(5000, function()
  return logged("pinned fmt --stdin dev-profile-warm.md")
end), true)

-- `mise run generate` rewrites the wrapper for the new pin; `mise install` adds the build.
local wrapper = work .. "/out/bin/dev-profile-dprint"
local from, to = "/installs/dprint/" .. os.getenv("PIN") .. "/", "/installs/dprint/9.9.9/"
vim.fn.writefile(vim.tbl_map(function(line)
  return (line:gsub(vim.pesc(from), to))
end, vim.fn.readfile(wrapper)), wrapper)
expect("a pin that is not installed yet runs mise's shim", save(), "shim")
local new_build = work .. "/data" .. to .. "dprint"
vim.fn.mkdir(vim.fs.dirname(new_build), "p")
vim.fn.writefile({ "#!/bin/sh", "echo newpin" }, new_build)
vim.fn.setfperm(new_build, "rwxr-xr-x")
expect("the next save of the running Neovim runs the new pin", save(), "newpin")

os.remove(work .. "/data/installs/dprint/9.9.9/dprint")
os.remove(work .. "/data/shims/dprint")
expect("without the build or the shim, dprint on PATH", save(), "path")
EOF

: >"${work}/calls"
WORK="${work}" PIN="${pin}" CONFORM_LUA="${CONFORM_LUA:-${root}/conform.lua}" DEV_PROFILE_OUT="${work}/out" \
	MISE_DATA_DIR="${work}/data" DP_CALLS="${work}/calls" PATH="${work}/path:/usr/bin:/bin" \
	"${nvim_bin}" --headless --clean -l "${work}/check.lua" || fail "nvim run (see above)"
[[ ! -e "${work}/mise-called" ]] || fail "a save must never run mise"

# Without MISE_DATA_DIR the wrapper finds mise's default data directory.
stub "${work}/home/.local/share/mise/installs/dprint/${pin}/dprint" default
got="$(env -u MISE_DATA_DIR -u XDG_DATA_HOME HOME="${work}/home" PATH="${work}/path:/usr/bin:/bin" "${out}/bin/dev-profile-dprint" fmt)"
[[ "${got}" == default ]] || fail "the default mise data directory: got ${got}"
echo "conform-resolve fixture ok"
