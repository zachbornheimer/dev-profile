-- ~/.config/nvim/lua/user/typo.lua
-- Command: <leader>bpptypo (in visual mode)
-- Description: Runs "./route typo --original="<selected>" --corrected="<input>""
-- only when inside /Users/zbornheimer/Zysys/Software/insurance

local M = {}

--- Get text currently selected in visual mode
--- Works across multiple uses, lines, and modes.
local function get_visual_selection()
  local mode = vim.fn.mode()
  if mode ~= "v" and mode ~= "V" and mode ~= "\22" then
    -- Re-select last visual selection
    vim.cmd("normal! gv")
  end

  -- Yank current visual selection into register z
  vim.cmd('normal! "zy')
  return vim.fn.getreg("z")
end

--- Run typo correction command in insurance directory
function M.typo_correct(reflexive)
  local cwd = vim.fn.getcwd()
  local target_dir = "/Users/zbornheimer/Dropbox/Zysys/Software/insurance"

  -- ensure we’re in the target directory
  if cwd ~= target_dir then
    vim.notify("not in insurance directory: " .. cwd, vim.log.levels.WARN)
    return
  end
  vim.notify("In insurance directory: " .. cwd, vim.log.levels.INFO)

  -- Always reselect and yank the active region
  local selection = get_visual_selection()
  if not selection or selection == "" then
    vim.notify("No text selected.", vim.log.levels.ERROR)
    return
  end

  -- Ask user for corrected text
  local corrected = ""
  if reflexive == true then
    corrected = vim.fn.input("Corrected text for " .. selection .. ": (enter self for the same as input) ", "")
    if corrected == "" then
      vim.notify("Correction cancelled.", vim.log.levels.INFO)
      return
    end
    if corrected == "self" then
      corrected = selection
    end
  else
    corrected = selection
  end

  -- Confirm execution
  local cmd = string.format('./route typo --original="%s" --corrected="%s"', selection, corrected)
  if reflexive == false then
    cmd = string.format(
      'doppler run -- python3 python/scripts/save_spelling.py --original="%s" --corrected="%s"',
      selection,
      corrected
    )
  else
    local confirm = vim.fn.input("Run typo command? " .. cmd .. " (y/n): ", "")
    if confirm:lower() ~= "y" then
      vim.notify("Aborted.", vim.log.levels.INFO)
      return
    end
  end

  -- Execute the command
  vim.cmd("!" .. cmd)
  vim.notify("Executed: " .. cmd, vim.log.levels.INFO)
end

-- Map <leader>bpptypo for visual mode
--
local cwd = vim.fn.getcwd()
local target_dir = "/Users/zbornheimer/Dropbox/Zysys/Software/insurance"

-- ensure we’re in the target directory
if cwd == target_dir then
  vim.keymap.set("v", "<leader>t", function()
    require("zach.bpp").typo_correct(true)
  end, { desc = "Run typo correction route", silent = true })
  vim.keymap.set("v", "<leader>s", function()
    require("zach.bpp").typo_correct(false)
  end, { desc = "Run typo correction route for self without reflection", silent = true })
end

return M
