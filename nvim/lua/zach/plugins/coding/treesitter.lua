-- nvim-treesitter main (Nvim 0.12+). master is archived and crashes the
-- built-in highlighter on markdown fenced code blocks (nil :range()).
--
-- Highlighting/folds come from Neovim; this plugin installs parsers + queries
-- and wires experimental indent + autotag.
return {
  "nvim-treesitter/nvim-treesitter",
  branch = "main",
  lazy = false, -- plugin does not support lazy-loading
  build = ":TSUpdate",
  dependencies = {
    "windwp/nvim-ts-autotag",
  },
  config = function()
    local nvim_treesitter = require("nvim-treesitter")

    nvim_treesitter.setup({
      -- Prefer these parsers/queries over Neovim's bundled copies when both exist.
      install_dir = vim.fn.stdpath("data") .. "/site",
    })

    -- Parsers used by this config. Markdown is bundled with Nvim 0.12 and
    -- auto-started via runtime/ftplugin/markdown.lua — keep it off this list
    -- so we don't fight the built-in stack (the previous master-branch
    -- highlight.disable never applied to vim.treesitter.start()).
    local ensure = {
      "bash",
      "c",
      "c_sharp",
      "css",
      "dockerfile",
      "gitignore",
      "graphql",
      "html",
      "javascript",
      "json",
      "lua",
      "perl",
      "php",
      "python",
      "query",
      "tsx",
      "typescript",
      "vim",
      "vimdoc",
      "yaml",
    }

    -- Async install; no-op when already present at the expected revision.
    nvim_treesitter.install(ensure)

    -- Skip parsing above this size: a 2026-08-28 nvim OOM (one process hit
    -- ~20GB RSS) traced to treesitter parsing the 5MB WordPress stub file
    -- (vendor/php-stubs/wordpress-stubs/wordpress-stubs.php) with no cap.
    local max_parse_bytes = 512 * 1024
    local function file_too_large(buf)
      local ok, stat = pcall(vim.uv.fs_stat, vim.api.nvim_buf_get_name(buf))
      return ok and stat and stat.size > max_parse_bytes
    end

    -- Enable treesitter highlight for filetypes Neovim doesn't auto-start.
    -- Markdown/lua already call vim.treesitter.start() in their ftplugins.
    local auto_start = {
      "bash",
      "c",
      "cs",
      "css",
      "dockerfile",
      "gitignore",
      "graphql",
      "html",
      "javascript",
      "json",
      "perl",
      "php",
      "python",
      "query",
      "typescript",
      "typescriptreact",
      "javascriptreact",
      "vim",
      "yaml",
    }

    vim.api.nvim_create_autocmd("FileType", {
      group = vim.api.nvim_create_augroup("zach_treesitter_start", { clear = true }),
      pattern = auto_start,
      callback = function(ev)
        if file_too_large(ev.buf) then
          return
        end
        -- pcall: missing parser should not throw into the UI
        pcall(vim.treesitter.start, ev.buf)
      end,
    })

    -- Indent is experimental; skip markdown (regex indent is more reliable).
    local indent_ft = {
      "bash",
      "c",
      "cs",
      "css",
      "html",
      "javascript",
      "json",
      "lua",
      "perl",
      "php",
      "python",
      "typescript",
      "typescriptreact",
      "javascriptreact",
      "yaml",
    }

    vim.api.nvim_create_autocmd("FileType", {
      group = vim.api.nvim_create_augroup("zach_treesitter_indent", { clear = true }),
      pattern = indent_ft,
      callback = function(ev)
        if file_too_large(ev.buf) then
          return
        end
        vim.bo.indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
      end,
    })

    -- Autotag is its own plugin now (nvim-treesitter.configs.autotag is gone).
    local ok_autotag, autotag = pcall(require, "nvim-ts-autotag")
    if ok_autotag then
      autotag.setup()
    end
  end,
}
