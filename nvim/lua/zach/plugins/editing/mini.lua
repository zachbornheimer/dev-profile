-- mini.surround (add/change/delete surrounding quotes, brackets, tags) +
-- mini.ai (smarter text objects: ci(, va", function/argument objects).
-- surround is g-prefixed so plain `s` stays Flash's jump key.
return {
  "echasnovski/mini.nvim",
  version = "*",
  event = "VeryLazy",
  config = function()
    require("mini.surround").setup({
      mappings = {
        add = "gsa", -- gsa<motion><char>  e.g. gsaiw"  → surround word with "
        delete = "gsd", -- gsd"             → delete surrounding "
        replace = "gsr", -- gsr"(           → change " to (
        find = "gsf",
        find_left = "gsF",
        highlight = "gsh",
        update_n_lines = "gsn",
      },
    })
    require("mini.ai").setup()
  end,
}
