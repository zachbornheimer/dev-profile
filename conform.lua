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

-- Saves run dprint's real binary, found with `mise which` for the directory
-- dprint runs in, not whatever PATH holds. PATH names a versioned install
-- directory, so a process started before a pin change keeps running the old
-- binary: 0.61.1 took 0.7 to 1.6 s per save where the pinned build takes 0.1 s.
-- Calling mise's shim on every save avoids that but costs about 40 ms each
-- time, two thirds of a save, so the resolution is cached per directory. An
-- entry is dropped when its binary is gone or when the mise config files that
-- picked it change, so a pin change takes effect on the next save.
local RESOLVE_TIMEOUT_MS = 5000

local function shim_command()
  local shim = (vim.env.MISE_DATA_DIR or vim.fn.expand("~/.local/share/mise")) .. "/shims/dprint"
  return vim.fn.executable(shim) == 1 and shim or "dprint"
end

local function mtime(file)
  local stat = file and vim.uv.fs_stat(file)
  return stat and (stat.mtime.sec .. "." .. stat.mtime.nsec) or ""
end

-- The global profile plus the nearest project config: what mise reads to pick a version.
local function pin_stamp(cwd)
  local project = vim.fs.find({ "mise.toml", ".mise.toml" }, { path = cwd, upward = true })[1]
  return mtime(out .. "/mise-profile.toml") .. "|" .. mtime(project)
end

local resolved = {}

local function dprint_command(cwd)
  local stamp = pin_stamp(cwd)
  local hit = resolved[cwd]
  if hit and hit.stamp == stamp and vim.uv.fs_stat(hit.bin) then
    return hit.bin
  end
  local mise = vim.fn.exepath("mise")
  if mise == "" then
    return shim_command()
  end
  local ok, result = pcall(function()
    return vim.system({ mise, "which", "dprint" }, { cwd = cwd, text = true }):wait(RESOLVE_TIMEOUT_MS)
  end)
  local bin = ok and result.code == 0 and vim.trim(result.stdout or "") or ""
  if bin == "" or vim.fn.executable(bin) ~= 1 then
    return shim_command()
  end
  resolved[cwd] = { bin = bin, stamp = stamp }
  return bin
end

-- A dprint run first downloads and compiles every plugin its config lists. With
-- the profile's twelve that takes far longer than FORMAT_TIMEOUT_MS (about 9 s
-- of compiling alone), so with an empty cache, as after a macOS storage purge,
-- conform kills each save at the timeout and formats nothing until the cache
-- fills. One background run at startup, with no short timeout, fills it before
-- the first save; with a warm cache it costs about a tenth of a second.
local WARM_TIMEOUT_MS = 180000

local function warm_dprint_cache()
  local dprint = shim_command()
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
    formatters = {
      dprint = {
        command = function(self, ctx)
          return dprint_command(dprint_cwd(self, ctx))
        end,
        cwd = dprint_cwd,
      },
    },
    format_on_save = function(bufnr)
      local ft = vim.bo[bufnr].filetype
      if vim.g.disable_autoformat or vim.b[bufnr].disable_autoformat or skip[ft] then
        return nil
      end
      return { timeout_ms = FORMAT_TIMEOUT_MS, lsp_format = "fallback" }
    end,
  },
}
