-- Conform is the single owner of "format this buffer": the Dev Profile manifest
-- that `mise run generate` writes decides which filetypes get formatted, and
-- dprint decides how.
--
-- dprint is reached through its language server whenever one can start, and
-- through the command line only when it cannot. A dprint process pays the whole
-- plugin list of the config it resolves on every run (~0.8 s for the profile's
-- twelve plugins, ~9 s with a cold compile cache), while the server pays that
-- once and then answers in milliseconds. The server also resolves the nearest
-- dprint config per document, so a project config wins over the global one and
-- files with no config of their own still get the global defaults.
local out = vim.env.DEV_PROFILE_OUT or vim.fn.expand("~/.local/share/dev-profile")
local path = out .. "/profile.json"

local FORMAT_TIMEOUT_MS = 3000
local SERVER_NAME = "dprint"

local formatters_by_ft, skipped_ft = {}, {}
local dprint_ft = {}
if vim.fn.filereadable(path) == 1 then
  local profile = vim.json.decode(table.concat(vim.fn.readfile(path), "\n"))
  for ft, spec in pairs(profile.filetypes) do
    formatters_by_ft[ft] = spec.formatters
    skipped_ft[ft] = not spec.format_on_save
    for _, formatter in ipairs(spec.formatters) do
      if formatter == SERVER_NAME then
        dprint_ft[ft] = true
      end
    end
  end
else
  vim.notify("dev-profile: " .. path .. " missing; run `mise run generate`", vim.log.levels.WARN)
end

local server_id

local function server()
  if server_id then
    local running = vim.lsp.get_client_by_id(server_id)
    if running then
      return running
    end
  end
  if vim.fn.executable(SERVER_NAME) ~= 1 then
    return nil
  end
  local capabilities = vim.lsp.protocol.make_client_capabilities()
  capabilities.workspace = capabilities.workspace or {}
  capabilities.workspace.configuration = true
  server_id = vim.lsp.start({
    name = SERVER_NAME,
    cmd = { SERVER_NAME, "lsp" },
    -- A document with no dprint config of its own is formatted with the global
    -- config instead of being rejected.
    init_options = { useGlobalConfig = true },
    settings = { useGlobalConfig = true },
    capabilities = capabilities,
  })
  return server_id and vim.lsp.get_client_by_id(server_id)
end

local function attached_server(bufnr)
  for _, client in ipairs(vim.lsp.get_clients({ bufnr = bufnr, name = SERVER_NAME })) do
    return client
  end
  return nil
end

-- dprint only formats files under its working directory, so the command line
-- runs from the nearest config directory, or from the buffer's own directory
-- when it has none, where dprint falls back to the global config.
local function dprint_cwd(self, ctx)
  local root = require("conform.util").root_file({
    "dprint.json",
    "dprint.jsonc",
    ".dprint.json",
    ".dprint.jsonc",
  })(self, ctx)
  return root or vim.fs.dirname(ctx.filename)
end

local function format(bufnr, timeout_ms)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  timeout_ms = timeout_ms or FORMAT_TIMEOUT_MS
  local client = attached_server(bufnr)
  if client then
    local formatted = pcall(vim.lsp.buf.format, {
      bufnr = bufnr,
      timeout_ms = timeout_ms,
      filter = function(candidate)
        return candidate.id == client.id
      end,
    })
    if formatted then
      return
    end
  end
  require("conform").format({ bufnr = bufnr, timeout_ms = timeout_ms, lsp_format = "never" })
end

local group = vim.api.nvim_create_augroup("dev_profile_format", { clear = true })

-- One server per session covers every project: it resolves config per document.
vim.api.nvim_create_autocmd("FileType", {
  group = group,
  callback = function(args)
    if not dprint_ft[vim.bo[args.buf].filetype] then
      return
    end
    local client = server()
    if client then
      vim.lsp.buf_attach_client(args.buf, client.id)
    end
  end,
})

vim.api.nvim_create_autocmd("BufWritePre", {
  group = group,
  callback = function(args)
    local bufnr = args.buf
    local ft = vim.bo[bufnr].filetype
    if vim.g.disable_autoformat or vim.b[bufnr].disable_autoformat or skipped_ft[ft] or not formatters_by_ft[ft] then
      return
    end
    format(bufnr)
  end,
})

return {
  "stevearc/conform.nvim",
  opts = {
    formatters_by_ft = formatters_by_ft,
    formatters = { dprint = { cwd = dprint_cwd } },
    -- Saving is driven by the BufWritePre autocmd above so that both the server
    -- and the command line reach the same decision point.
    format_on_save = false,
  },
}
