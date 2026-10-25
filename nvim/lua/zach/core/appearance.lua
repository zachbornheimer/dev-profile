-- macOS appearance → vim.o.background
-- Same signal kitty uses for light-theme.auto / dark-theme.auto:
--   AppleInterfaceStyle = "Dark"  → dark  (Tomorrow Night)
--   key unset (defaults fails)    → light (Tomorrow)
-- Cache defaults read: FocusGained fires often; shelling out every time
-- costs ~100–300ms even when the theme did not change.

local M = {}

local CACHE_TTL_S = 2
local NS_PER_S = 1000000000
local CACHE_TTL_NS = CACHE_TTL_S * NS_PER_S
local cached_background ---@type string|nil
local cache_ns ---@type number|nil

local function read_macos_background()
  vim.fn.system({ "defaults", "read", "-g", "AppleInterfaceStyle" })
  return vim.v.shell_error == 0 and "dark" or "light"
end

function M.preferred_background()
  if vim.fn.has("macunix") ~= 1 then
    return "dark"
  end
  local now = vim.uv.hrtime()
  if cached_background ~= nil and cache_ns ~= nil and (now - cache_ns) < CACHE_TTL_NS then
    return cached_background
  end
  cached_background = read_macos_background()
  cache_ns = now
  return cached_background
end

--- Set vim.o.background from the OS. Returns true if the value changed.
function M.sync_background()
  local want = M.preferred_background()
  if vim.o.background == want then
    return false
  end
  vim.o.background = want
  return true
end

return M
