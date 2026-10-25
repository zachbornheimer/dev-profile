-- `gx` opens what is under the cursor: URLs, `#123` issues (via the git
-- remote), plugin specs like "folke/snacks.nvim", package.json / Brewfile /
-- go import lines. With nothing linkable it web-searches the word.
return {
  "chrishrb/gx.nvim",
  keys = { { "gx", "<cmd>Browse<cr>", mode = { "n", "x" }, desc = "Open link under cursor" } },
  cmd = { "Browse" },
  init = function()
    vim.g.netrw_nogx = 1 -- the plugin owns gx
  end,
  submodules = false, -- submodules are test vendoring only
  -- "folke/snacks.nvim" also parses as a bare domain; without this every gx on
  -- a plugin spec stops at a "Multiple patterns match" prompt. Handlers run
  -- specific-first, so the top match is the right one.
  opts = { select_prompt = false },
}
