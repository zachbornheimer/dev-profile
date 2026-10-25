-- Per-directory session: reopen nvim in a project and restore your buffers/
-- layout. Pairs with the kitty project sessions. Leader is "," so: ,qs etc.
return {
  "folke/persistence.nvim",
  event = "BufReadPre",
  opts = {},
  keys = {
    {
      "<leader>qs",
      function()
        require("persistence").load()
      end,
      desc = "Restore session (this dir)",
    },
    {
      "<leader>ql",
      function()
        require("persistence").load({ last = true })
      end,
      desc = "Restore last session",
    },
    {
      "<leader>qd",
      function()
        require("persistence").stop()
      end,
      desc = "Stop saving session",
    },
  },
}
