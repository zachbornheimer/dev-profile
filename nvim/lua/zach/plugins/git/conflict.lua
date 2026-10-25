-- Highlights merge-conflict hunks and resolves them in place.
-- The plugin's default `co/ct/cb/c0` are buffer-local but shadow real change
-- commands (`ct{char}`, `cb`, `c0`) in every conflicted file, so the choose
-- keys live under <leader>m instead.
return {
  "akinsho/git-conflict.nvim",
  version = "*",
  event = { "BufReadPre", "BufNewFile" },
  opts = {
    default_mappings = {
      ours = "<leader>mo",
      theirs = "<leader>mt",
      both = "<leader>mb",
      none = "<leader>m0",
      next = "]x",
      prev = "[x",
    },
  },
  config = function(_, opts)
    require("git-conflict").setup(opts)
    -- It watches the repo's .git recursively and stops that watcher in
    -- VimLeavePre. Stopping an fs_event on Dropbox blocks quit for seconds
    -- (see core/quit.lua), which unrefs the handle instead, so drop this one.
    vim.api.nvim_clear_autocmds({ event = "VimLeavePre", group = "GitConflictCommands" })
  end,
}
