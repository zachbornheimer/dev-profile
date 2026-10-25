local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    "git",
    "clone",
    "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable", -- latest stable release
    lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

-- One directory per role under lua/zach/plugins/; a spec file belongs to the
-- directory that describes what it does for the user. See LAYOUT.md.
require("lazy").setup({
  spec = {
    { import = "zach.plugins.ui" }, -- colors, which-key, snacks, command line
    { import = "zach.plugins.editing" }, -- motions, text objects, quickfix, links
    { import = "zach.plugins.coding" }, -- completion, LSP, treesitter, formatting
    { import = "zach.plugins.git" },
    { import = "zach.plugins.integrations" }, -- herdr, kitty, browser previews
  },
})
