-- Conform is only the Neovim frontend to dprint. Which filetypes it formats
-- comes from the Dev Profile manifest that `mise run generate` writes.
local out = vim.env.DEV_PROFILE_OUT or vim.fn.expand("~/.local/share/dev-profile")
local path = out .. "/profile.json"

local formatters_by_ft, skip = {}, {}
if vim.fn.filereadable(path) == 1 then
  local profile = vim.json.decode(table.concat(vim.fn.readfile(path), "\n"))
  for ft, spec in pairs(profile.filetypes) do
    formatters_by_ft[ft] = spec.formatters
    skip[ft] = not spec.format_on_save
  end
else
  vim.notify("dev-profile: " .. path .. " missing; run `mise run generate`", vim.log.levels.WARN)
end

-- dprint only formats files under its working directory. Files outside any
-- project config (scratch files, /tmp) run from their own directory, where
-- dprint falls back to the global ~/.config/dprint config.
local function dprint_cwd(self, ctx)
  local root = require("conform.util").root_file({
    "dprint.json",
    "dprint.jsonc",
    ".dprint.json",
    ".dprint.jsonc",
  })(self, ctx)
  return root or vim.fs.dirname(ctx.filename)
end

return {
  "stevearc/conform.nvim",
  opts = {
    formatters_by_ft = formatters_by_ft,
    formatters = { dprint = { cwd = dprint_cwd } },
    format_after_save = function(bufnr)
      local ft = vim.bo[bufnr].filetype
      if vim.g.disable_autoformat or vim.b[bufnr].disable_autoformat or skip[ft] then
        return nil
      end
      return { lsp_format = "fallback" }
    end,
  },
}
