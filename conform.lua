-- Conform is only the Neovim frontend to dprint. Which filetypes it formats
-- comes from the Dev Profile manifest that `mise run generate` writes.
local out = vim.env.DEV_PROFILE_OUT or vim.fn.expand("~/.local/share/dev-profile")
local path = out .. "/profile.json"

local FORMAT_TIMEOUT_MS = 3000

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

-- Generated from profile.pkl's dprint pin: always that build, whatever PATH holds.
local dprint = out .. "/bin/dev-profile-dprint"

-- A dprint run first downloads and compiles every plugin its config lists. With
-- the profile's twelve that takes far longer than FORMAT_TIMEOUT_MS (about 9 s
-- of compiling alone), so with an empty cache, as after a macOS storage purge,
-- conform kills each save at the timeout and formats nothing until the cache
-- fills. One background run at startup, with no short timeout, fills it before
-- the first save; with a warm cache it costs about a tenth of a second.
local WARM_TIMEOUT_MS = 180000

local function warm_dprint_cache()
  if vim.fn.executable(dprint) ~= 1 then
    return
  end
  vim.system({ dprint, "fmt", "--stdin", "dev-profile-warm.md" }, {
    stdin = "",
    cwd = vim.fn.getcwd(),
    timeout = WARM_TIMEOUT_MS,
  }, function(result)
    if result.code ~= 0 then
      vim.schedule(function()
        local reason = vim.split(result.stderr or "", "\n", { trimempty = true })[1] or "exit " .. result.code
        vim.notify("dprint: plugin cache warm-up failed: " .. reason, vim.log.levels.WARN)
      end)
    end
  end)
end

return {
  "stevearc/conform.nvim",
  init = function()
    vim.api.nvim_create_autocmd("VimEnter", {
      group = vim.api.nvim_create_augroup("dev_profile_dprint_warm", { clear = true }),
      once = true,
      callback = warm_dprint_cache,
    })
  end,
  opts = {
    formatters_by_ft = formatters_by_ft,
    formatters = { dprint = { command = dprint, cwd = dprint_cwd } },
    format_on_save = function(bufnr)
      local ft = vim.bo[bufnr].filetype
      if vim.g.disable_autoformat or vim.b[bufnr].disable_autoformat or skip[ft] then
        return nil
      end
      return { timeout_ms = FORMAT_TIMEOUT_MS, lsp_format = "fallback" }
    end,
  },
}
