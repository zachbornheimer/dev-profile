-- Match kitty: Rosé Pine Dawn under macOS light, Moon under dark (kitty's
-- light-theme.auto.conf / dark-theme.auto.conf). variant "auto" picks from
-- 'background', which zach.core.appearance keeps on the macOS setting.
--
-- The background stays opaque. kitty's background_opacity only applies to
-- cells in the terminal's default background, so a transparent Normal lets
-- the window behind kitty set the contrast: Dawn's text measured 1.7:1 over
-- a dark desktop. zach.core.contrast holds the floor on the opaque one.
return {
  "rose-pine/neovim",
  name = "rose-pine",
  lazy = false,
  priority = 1000,
  config = function()
    local appearance = require("zach.core.appearance")
    require("rose-pine").setup({ variant = "auto", dark_variant = "moon" })
    vim.cmd.colorscheme("rose-pine")

    -- Changing 'background' reloads the loaded colorscheme on its own;
    -- nested lets that reload fire ColorScheme (zach.core.contrast).
    vim.api.nvim_create_autocmd("FocusGained", {
      desc = "Follow macOS light/dark like kitty",
      nested = true,
      callback = function()
        appearance.sync_background()
      end,
    })
  end,
}
