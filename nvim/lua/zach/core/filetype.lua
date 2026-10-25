-- Filetype the buffer would not get on its own.
--
-- NVIM_FILETYPE names the syntax for this launch (herdr oneshot, gum's editor).
-- A uv script has no extension and a `#!/usr/bin/env -S uv run --script`
-- shebang. Nvim strips `env -S`, sees `uv`, and the `#` fallback calls it
-- conf. The PEP 723 block is what makes it Python.

local UV_SHEBANG = "^#!.*/env%s+%-S%s+uv%s+run%s+%-%-script"
local PEP723 = "^#%s*///%s*script%s*$"

local function requested()
  local name = vim.env.NVIM_FILETYPE
  if not name or name == "" then
    return nil
  end
  if not name:match("^[%w_+%-]+$") then
    return nil
  end
  return name
end

local function uv_script(bufnr)
  local lines = vim.api.nvim_buf_get_lines(bufnr, 0, 8, false)
  if not lines[1] or not lines[1]:match(UV_SHEBANG) then
    return false
  end
  for i = 2, #lines do
    if lines[i]:match(PEP723) then
      return true
    end
  end
  return false
end

local function apply(bufnr)
  if not vim.api.nvim_buf_is_valid(bufnr) or vim.bo[bufnr].buftype ~= "" then
    return
  end
  local name = requested()
  if not name and uv_script(bufnr) then
    name = "python"
  end
  if not name or vim.bo[bufnr].filetype == name and vim.bo[bufnr].syntax == name then
    return
  end
  -- Setting filetype fires FileType, whose ftplugin sets syntax and can clear
  -- it again. Reapply once that event has finished.
  vim.schedule(function()
    if not vim.api.nvim_buf_is_valid(bufnr) then
      return
    end
    if vim.bo[bufnr].filetype ~= name then
      vim.bo[bufnr].filetype = name
    end
    if vim.bo[bufnr].syntax ~= name then
      vim.bo[bufnr].syntax = name
    end
  end)
end

local group = vim.api.nvim_create_augroup("zach_filetype", { clear = true })

-- BufReadPost: detection has finished. FileType: a later detector (the `#`
-- fallback that calls a uv script `conf`) must not undo the choice.
vim.api.nvim_create_autocmd({ "BufReadPost", "BufNewFile", "FileType" }, {
  group = group,
  callback = function(ev)
    apply(ev.buf)
  end,
})

apply(vim.api.nvim_get_current_buf())

return {
  apply = apply,
}
