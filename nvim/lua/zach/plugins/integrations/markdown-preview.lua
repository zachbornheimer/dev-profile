-- markdown-preview.nvim — preview Markdown in browser with live updates
return {
  "iamcco/markdown-preview.nvim",
  version = "*",
  build = { "sh -c 'cd app && npm install'" },
  ft = { "markdown" },
  cmd = { "MarkdownPreview", "MarkdownPreviewStop", "MarkdownPreviewToggle" },
  init = function()
    vim.g.mkdp_filetypes = { "markdown" }
  end,
}
