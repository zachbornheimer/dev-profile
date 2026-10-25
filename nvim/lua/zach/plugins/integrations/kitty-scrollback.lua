-- Deluxe "output → nvim": opens kitty's scrollback (or the last command's
-- output) in nvim with COLORS PRESERVED, links clickable, and easy copy —
-- the upgrade over the plain-text scrollback-nvim pager script. Wired from
-- kitty.conf via the generated kitten (see the kitty-scrollback block there).
return {
  "mikesmithgh/kitty-scrollback.nvim",
  lazy = true,
  cmd = {
    "KittyScrollbackGenerateKittens",
    "KittyScrollbackCheckHealth",
    "KittyScrollbackGenerateCommandLineEditing",
  },
  event = { "User KittyScrollbackLaunch" },
  config = function()
    require("kitty-scrollback").setup()
  end,
}
