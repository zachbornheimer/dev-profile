-- plugins/coding/mason.lua
-- LSP servers + tools, installed and enabled only when a relevant filetype opens.

local TYPESCRIPT_FILETYPES = {
  "javascript",
  "javascriptreact",
  "typescript",
  "typescriptreact",
  "vue",
}

-- Return the TypeScript plugin bundled with vue-language-server.
local function vue_typescript_plugin()
  local mason_root = vim.env.MASON or vim.fs.joinpath(vim.fn.stdpath("data"), "mason")

  return {
    name = "@vue/typescript-plugin",
    location = vim.fs.joinpath(
      mason_root,
      "packages",
      "vue-language-server",
      "node_modules",
      "@vue",
      "language-server"
    ),
    languages = { "vue" },
    configNamespace = "typescript",
  }
end

-- csharp-ls uses MSBuildLocator / hostfxr. GUI and tmux non-login shells
-- often have no mise/homebrew on PATH, which surfaces as
-- "No .NET SDKs were found" on initialize.
local function csharp_ls_cmd_env()
  local path = vim.env.PATH or ""
  local prepend = {
    vim.fn.stdpath("data") .. "/mason/bin",
    vim.fn.expand("~/.local/share/mise/shims"),
    "/opt/homebrew/bin",
    "/usr/local/share/dotnet",
  }
  for i = #prepend, 1, -1 do
    local dir = prepend[i]
    if dir ~= "" and not path:find(dir, 1, true) then
      path = dir .. ":" .. path
    end
  end

  local env = { PATH = path }
  if vim.env.DOTNET_ROOT == nil or vim.env.DOTNET_ROOT == "" then
    local cellar = vim.fn.glob("/opt/homebrew/Cellar/dotnet/*/libexec", false, true)[1]
    env.DOTNET_ROOT = cellar or "/usr/local/share/dotnet"
  end
  return env
end

-- Mise ships a typescript-language-server shim that is inactive unless a
-- project opts into that tool. It is first on PATH, so a name lookup never
-- reaches Mason, the server never initializes, and gd reports that no
-- attached client supports textDocument/definition. Exec the Mason binary.
local function typescript_language_server_cmd()
  local mason_root = vim.env.MASON or vim.fs.joinpath(vim.fn.stdpath("data"), "mason")
  return {
    vim.fs.joinpath(mason_root, "bin", "typescript-language-server"),
    "--stdio",
  }
end

-- Front-end files share TypeScript + Vue tooling.
-- vue_ls itself only attaches to Vue buffers.
local FRONTEND = {
  servers = {
    {
      name = "ts_ls",
      package = "typescript-language-server",
      config = function()
        return {
          cmd = typescript_language_server_cmd(),
          filetypes = TYPESCRIPT_FILETYPES,
          init_options = {
            hostInfo = "neovim",
            plugins = { vue_typescript_plugin() },
          },
        }
      end,
    },
    {
      name = "vue_ls",
      package = "vue-language-server",
    },
  },
}

local LANGUAGES = {
  go = {
    servers = {
      {
        name = "gopls",
        package = "gopls",
        config = {
          settings = {
            gopls = {
              gofumpt = true,
              staticcheck = true,
            },
          },
        },
      },
    },
    tools = { "golangci-lint", "delve" },
  },

  php = {
    servers = {
      {
        name = "intelephense",
        package = "intelephense",
      },
    },
    tools = { "php-cs-fixer" },
  },

  python = {
    servers = {
      {
        name = "pyright",
        package = "pyright",
      },
    },
    tools = { "black" },
  },

  lua = {
    servers = {
      {
        name = "lua_ls",
        package = "lua-language-server",
      },
    },
    tools = { "stylua" },
  },

  ruby = {
    servers = {
      {
        name = "ruby_lsp",
        package = "ruby-lsp",
      },
    },
    tools = { "rubocop" },
  },

  cs = {
    servers = {
      {
        name = "csharp_ls",
        package = "csharp-language-server",
        config = function()
          local handlers = {}
          local ok, csharpls_extended = pcall(require, "csharpls_extended")
          if ok then
            handlers["textDocument/definition"] = csharpls_extended.handler
            handlers["textDocument/typeDefinition"] = csharpls_extended.handler
            csharpls_extended.buf_read_cmd_bind()
          end

          return {
            cmd_env = csharp_ls_cmd_env(),
            cmd = function(dispatchers, config)
              return vim.lsp.rpc.start({ "csharp-ls", "--features", "metadata-uris" }, dispatchers, {
                cwd = config.cmd_cwd or config.root_dir,
                env = config.cmd_env,
                detached = config.detached,
              })
            end,
            handlers = handlers,
          }
        end,
      },
    },
    tools = { "csharpier" },
  },

  javascript = FRONTEND,
  javascriptreact = FRONTEND,
  typescript = FRONTEND,
  typescriptreact = FRONTEND,
  vue = FRONTEND,
}

local filetypes = vim.tbl_keys(LANGUAGES)

-- Track shared language configurations so, for example, the front-end stack
-- is only initialized once even if both TypeScript and Vue buffers are opened.
local setup_state = {}

-- Ensure Mason packages exist before starting servers that depend on them.
local function ensure_packages(packages, callback)
  if not packages or #packages == 0 then
    callback(true)
    return
  end

  local registry = require("mason-registry")
  local remaining = #packages
  local succeeded = true

  local function complete(package_name, installed)
    if not installed then
      succeeded = false
      vim.notify(("Failed to install Mason package: %s"):format(package_name), vim.log.levels.ERROR)
    end

    remaining = remaining - 1
    if remaining == 0 then
      callback(succeeded)
    end
  end

  for _, package_name in ipairs(packages) do
    local found, package = pcall(registry.get_package, package_name)

    if not found then
      complete(package_name, false)
    elseif package:is_installed() then
      complete(package_name, true)
    else
      local started, handle = pcall(function()
        return package:install()
      end)

      if not started then
        complete(package_name, false)
      else
        handle:once(
          "closed",
          vim.schedule_wrap(function()
            complete(package_name, package:is_installed())
          end)
        )
      end
    end
  end
end

-- Configure and enable every server required by this filetype.
local function setup_language(filetype)
  local language = LANGUAGES[filetype]
  if not language or setup_state[language] then
    return
  end

  setup_state[language] = "pending"

  local server_packages = vim.tbl_map(function(server)
    return server.package
  end, language.servers)

  ensure_packages(server_packages, function(success)
    if not success then
      setup_state[language] = nil
      return
    end

    for _, server in ipairs(language.servers) do
      local config = server.config

      if type(config) == "function" then
        config = config()
      end

      if config then
        vim.lsp.config(server.name, config)
      end
    end

    vim.lsp.enable(vim.tbl_map(function(server)
      return server.name
    end, language.servers))

    setup_state[language] = "ready"
  end)

  -- Auxiliary formatters/debuggers/linters may install independently.
  ensure_packages(language.tools or {}, function() end)
end

return {
  { "Decodetalkers/csharpls-extended-lsp.nvim", lazy = true },

  {
    "williamboman/mason.nvim",
    ft = filetypes,
    build = ":MasonUpdate",
    config = true,
  },

  {
    "williamboman/mason-lspconfig.nvim",
    ft = filetypes,
    dependencies = {
      "williamboman/mason.nvim",
      "neovim/nvim-lspconfig",
      "Decodetalkers/csharpls-extended-lsp.nvim",
    },
    config = function()
      require("mason-lspconfig").setup({
        automatic_enable = false,
      })

      vim.api.nvim_create_autocmd("LspAttach", {
        group = vim.api.nvim_create_augroup("zach_lsp_definition", { clear = true }),
        callback = function(args)
          vim.keymap.set("n", "gd", vim.lsp.buf.definition, {
            buffer = args.buf,
            desc = "LSP definition",
          })
        end,
      })

      -- Handle the buffer that caused this plugin to load.
      setup_language(vim.bo.filetype)

      -- Handle subsequently opened language buffers.
      vim.api.nvim_create_autocmd("FileType", {
        pattern = filetypes,
        callback = function(args)
          setup_language(vim.bo[args.buf].filetype)
        end,
      })
    end,
  },
}
