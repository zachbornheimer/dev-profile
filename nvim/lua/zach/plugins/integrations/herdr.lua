-- herdr-nvim, nvim half: comment lines/selections like a code review and send
-- them (or a bare path:line reference) to an agent pane in the same herdr
-- workspace. Keys: <leader>a + c comment, l list, s paste, S send, i ref.
--
-- The sidebar and file picker are the other half, a herdr plugin installed with
-- `herdr plugin install ChmaraX/herdr-nvim` and bound in
-- ~/.config/herdr/config.toml (prefix+e, prefix+o). The sidebar's own nvim
-- injects this module itself, so `cond` only decides whether a normal nvim
-- started inside a herdr pane gets the annotation keys.
return {
  "ChmaraX/herdr-nvim",
  cond = function()
    return (vim.env.HERDR_ENV or "") ~= ""
  end,
  event = "VeryLazy",
  cmd = "Herdr",
  opts = {},
}
