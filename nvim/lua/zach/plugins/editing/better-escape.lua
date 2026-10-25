-- `kj` leaves insert mode without lag. A plain `inoremap kj <Esc>` makes every
-- `k` wait `timeoutlen` for a possible `j`; this plugin types `k` at once and
-- takes it back (<BS><Esc>) only when `j` follows within the interval.
--
-- Only two-character shortcuts are supported, so the old three-key `lkj` is
-- gone: it kept the `l` lag and would now leave a stray `l` behind.
return {
  "nvim-zh/better-escape.vim",
  event = "VeryLazy",
  init = function()
    vim.g.better_escape_shortcut = { "kj" }
    vim.g.better_escape_interval = 150 -- ms between the two keys
  end,
}
