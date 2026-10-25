-- The single owner of "when does the file explorer appear".
-- Two triggers: an explicit toggle key, and the IDE-style auto-open on launch
-- for a real file. Directory launches are snacks' replace_netrw, not ours.

local perf = require("zach.core.perf")

local M = {}

local EXPLORER_SOURCE = "explorer"

-- Buffers where nvim is a throwaway editor for another tool (git commit/rebase,
-- hg, diff). Auto-opening a file tree over these is noise.
local NO_AUTO_OPEN_FILETYPES = {
  gitcommit = true,
  gitrebase = true,
  hgcommit = true,
  ["diff"] = true,
}

-- Opening a file from $HOME must not mount a 262-entry HOME tree
-- (Dropbox/iCloud children make the first explorer load multi-second).
local function is_home_dir(path)
  local normalize = function(p)
    return (vim.fn.fnamemodify(p, ":p"):gsub("/+$", ""))
  end
  return normalize(path) == normalize(vim.fn.expand("~"))
end

--- Whether the buffer nvim launched into justifies auto-opening the explorer.
---@param bufname string full path of the buffer
---@param buftype string vim.bo.buftype of the buffer
---@return boolean
local function launch_opens_explorer(bufname, buftype)
  if NO_AUTO_OPEN_FILETYPES[vim.bo.filetype] then
    return false
  end
  -- Throwaway-editor callers (herdr one-shot popup) opt out with this env var.
  if vim.env.NVIM_NO_EXPLORER then
    return false
  end
  -- Any special buffer (nofile from a stdin pipe, help, quickfix, terminal,
  -- directory) keeps the screen it was given.
  if buftype ~= "" then
    return false
  end
  if bufname == "" or vim.fn.filereadable(bufname) ~= 1 then
    return false
  end
  return not is_home_dir(vim.fn.getcwd())
end

---@return snacks.Picker[] explorers open in this tab
local function open_explorers()
  return require("snacks").picker.get({ source = EXPLORER_SOURCE })
end

--- Toggle the file explorer: close every open explorer, or open one.
function M.toggle()
  perf.span("explorer.toggle", function()
    local open = open_explorers()
    if #open > 0 then
      for _, picker in ipairs(open) do
        picker:close()
      end
      return
    end
    require("snacks").explorer()
  end)
end

--- Open the explorer with the cursor on the current buffer's file.
function M.reveal()
  perf.span("explorer.reveal", function()
    require("snacks").explorer.reveal()
  end)
end

--- Register the launch policy. Must run before the first buffer exists.
function M.install_launch_policy()
  vim.api.nvim_create_autocmd("VimEnter", {
    desc = "Auto-open the file explorer on launch, keeping focus in the editor",
    callback = function()
      perf.span("explorer.launch", function()
        local bufname = vim.api.nvim_buf_get_name(0)
        if not launch_opens_explorer(bufname, vim.bo.buftype) then
          return
        end
        -- show() focuses the tree before on_show runs, so this is the point
        -- where focus can be handed back to the editor: the launch keeps
        -- editing focus, as nvim-tree did with find_file.
        local editor_win = vim.api.nvim_get_current_win()
        require("snacks").explorer({
          on_show = function()
            if vim.api.nvim_win_is_valid(editor_win) then
              vim.api.nvim_set_current_win(editor_win)
            end
          end,
        })
      end)
    end,
  })
end

return M
