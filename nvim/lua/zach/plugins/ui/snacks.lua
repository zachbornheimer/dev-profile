-- snacks.nvim: replaces telescope (picker), nvim-tree (explorer) and
-- dressing.nvim (input), and adds the terminal/lazygit/notify/bigfile
-- pieces this config had no owner for.
--
-- lazy = false because quickfile has to render the first buffer before the
-- plugin load, and Snacks.* is called from keymaps regardless.
return {
  "folke/snacks.nvim",
  priority = 1000,
  lazy = false,
  ---@type snacks.Config
  opts = {
    picker = {
      enabled = true,
      sources = {
        explorer = {
          -- fs_event watchers on Dropbox/iCloud block nvim exit for ~15s after
          -- VimLeave (see zach.core.quit). nvim-tree ran with watchers off for
          -- the same reason, so the explorer keeps that policy.
          watch = false,
        },
      },
    },
    explorer = {
      enabled = true,
      -- `nvim <dir>` and `:e <dir>` open the explorer instead of netrw.
      -- Replace instead of coexist so no g:netrw_* option is load-bearing.
      replace_netrw = true,
    },
    input = { enabled = true },
    notifier = { enabled = true },
    -- 1.5MB+ buffers are exactly the Dropbox files that stall startup and
    -- attach: bigfile drops treesitter/LSP for them.
    bigfile = { enabled = true },
    quickfile = { enabled = true },
    terminal = { enabled = true },
    lazygit = { enabled = true },
  },
  init = function()
    -- The launch policy must be registered before any buffer exists, and the
    -- plugin itself is lazy = false, so VimEnter cannot fire first.
    require("zach.core.explorer").install_launch_policy()
  end,
  keys = {
    -- Finders: the same keys telescope owned, now backed by the picker. Its
    -- defaults already map <C-j>/<C-k> to move and <C-q> to send to quickfix,
    -- which is what telescope was configured to do by hand.
    {
      "<leader>ff",
      function()
        Snacks.picker.files()
      end,
      desc = "Find files",
    },
    {
      "<leader>fr",
      function()
        Snacks.picker.recent()
      end,
      desc = "Find recent files",
    },
    {
      "<leader>fs",
      function()
        Snacks.picker.grep()
      end,
      desc = "Find string in cwd",
    },
    {
      "<leader>fc",
      function()
        Snacks.picker.grep_word()
      end,
      desc = "Find string under cursor in cwd",
      mode = { "n", "x" },
    },

    -- Explorer: `zach.core.explorer` is the only owner of this behavior.
    {
      "<leader>ee",
      function()
        require("zach.core.explorer").toggle()
      end,
      desc = "Toggle file explorer",
    },
    {
      "<leader>E",
      function()
        require("zach.core.explorer").reveal()
      end,
      desc = "Reveal current file in explorer",
    },

    {
      "<leader>tt",
      function()
        Snacks.terminal()
      end,
      desc = "Toggle floating terminal",
      mode = { "n", "t" },
    },
    {
      "<leader>gg",
      function()
        Snacks.lazygit()
      end,
      desc = "Open lazygit",
    },
    {
      "<leader>sn",
      function()
        Snacks.notifier.show_history()
      end,
      desc = "Notification history",
    },
  },
}
