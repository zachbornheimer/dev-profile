-- Completion menu (the gap: you had LSP but no as-you-type completion).
-- blink.cmp — fast Rust matcher, wires into your existing vim.lsp servers,
-- built-in snippets. Default keymap leaves Tab to copilot.vim's ghost text.
return {
  "saghen/blink.cmp",
  version = "*", -- release tag ships the prebuilt fuzzy binary (no cargo build)
  lazy = false, -- load at startup so LSP capabilities register before servers attach
  opts = {
    keymap = { preset = "default" }, -- C-y accept · C-n/C-p move · C-space open · C-e hide
    appearance = { nerd_font_variant = "mono" },
    sources = { default = { "lsp", "path", "snippets", "buffer" } },
    completion = {
      documentation = { auto_show = true, auto_show_delay_ms = 250 },
      menu = { border = "rounded" },
      ghost_text = { enabled = false }, -- copilot.vim already shows ghost text
    },
    signature = { enabled = true },
    fuzzy = { implementation = "prefer_rust_with_warning" },
  },
  config = function(_, opts)
    require("blink.cmp").setup(opts)
    -- Advertise blink's completion capabilities to every LSP server (nvim 0.11+).
    vim.lsp.config("*", { capabilities = require("blink.cmp").get_lsp_capabilities() })
  end,
}
