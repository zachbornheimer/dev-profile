-- Quit must not wait on plugin teardown or libuv handle close.
-- Gitsigns detach walks git on Dropbox (~0.2-0.9s).
-- fs_event watches on Dropbox block process exit after VimLeave (~15s,
-- rc=1, 22 handles measured in this repo) when stop()/close() run on the
-- UI thread. Unref so the loop can exit without waiting on FSEvents.

local perf = require("zach.core.perf")

local GITSIGNS_GROUP = "gitsigns.attach"
local GITSIGNS_DETACH_DESC = "Gitsigns: detach from all buffers"
local QUIT_DESC = "Unref fs watches and skip gitsigns detach so quit does not stall"

local function skip_gitsigns_detach()
  pcall(vim.api.nvim_clear_autocmds, {
    event = "VimLeavePre",
    group = GITSIGNS_GROUP,
  })
  for _, au in ipairs(vim.api.nvim_get_autocmds({ event = "VimLeavePre" })) do
    if au.desc == GITSIGNS_DETACH_DESC and au.id then
      pcall(vim.api.nvim_del_autocmd, au.id)
    end
  end
end

local function force_stop_lsp()
  for _, client in ipairs(vim.lsp.get_clients()) do
    client.exit_timeout = false
    pcall(function()
      client:stop(true)
    end)
  end
end

--- Unref fs_event/fs_poll so the event loop can exit. Do not stop/close —
--- those block on Dropbox FSEvents on the UI thread (multi-second stalls).
---@return integer fs_event_count
---@return integer fs_poll_count
local function unref_fs_handles()
  local fs_event_count = 0
  local fs_poll_count = 0
  vim.uv.walk(function(handle)
    local kind = handle:get_type()
    if kind ~= "fs_event" and kind ~= "fs_poll" then
      return
    end
    if handle:is_closing() then
      return
    end
    if kind == "fs_event" then
      fs_event_count = fs_event_count + 1
    else
      fs_poll_count = fs_poll_count + 1
    end
    pcall(function()
      handle:unref()
    end)
  end)
  return fs_event_count, fs_poll_count
end

vim.api.nvim_create_autocmd("VimLeavePre", {
  desc = QUIT_DESC,
  callback = function()
    perf.span("quit.skip_gitsigns", skip_gitsigns_detach)
    perf.span("quit.stop_lsp", force_stop_lsp)
    local counts = {}
    perf.span("quit.unref_fs", function()
      counts.fs_event_count, counts.fs_poll_count = unref_fs_handles()
    end, counts)
  end,
})

vim.api.nvim_create_autocmd("VimLeave", {
  desc = "Unref leftover fs watches after shada write",
  callback = function()
    perf.span("quit.unref_fs_leave", unref_fs_handles)
  end,
})
