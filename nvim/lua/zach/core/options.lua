local opt = vim.opt -- for conciseness

-- line numbers
opt.relativenumber = true -- show relative line numbers
opt.number = true -- shows absolute line number on cursor line (when relative number is on)

-- tabs & indentation
opt.tabstop = 4 -- 4 spaces for tabs (prettier default)
opt.shiftwidth = 4 -- 4 spaces for indent width
opt.expandtab = true -- expand tab to spaces
opt.autoindent = true -- copy indent from current line when starting new one
opt.shiftround = true
opt.smarttab = true

-- line wrapping
opt.wrap = false -- disable line wrapping
opt.linebreak = true -- wrap on word boundaries when wrap is on
opt.breakindent = true -- keep indent on wrapped continuation lines

-- search settings
opt.ignorecase = true -- ignore case when searching
opt.smartcase = true -- if you include mixed case in your search, assumes you want case-sensitive

-- cursor line
opt.cursorline = false -- highlight the current cursor line

-- appearance

-- turn on termguicolors for nightfly colorscheme to work
-- (have to use iterm2 or any other true color terminal)
opt.termguicolors = true
-- Follow macOS light/dark (same source as kitty theme). Not hardcoded dark.
opt.background = require("zach.core.appearance").preferred_background()
opt.signcolumn = "yes" -- show sign column so that text doesn't shift

-- backspace
opt.backspace = "indent,eol,start" -- allow backspace on indent, end of line or insert mode start position

-- clipboard
--opt.clipboard:append("unnamedplus") -- use system clipboard as default register

-- split windows
opt.splitright = true -- split vertical window to the right
opt.splitbelow = true -- split horizontal window to the bottom

-- undo

-- Check if the undo directory exists; if not, create it
local undo_dir = vim.fn.expand("$HOME") .. "/.VIM_UNDO_FILES"
if vim.fn.isdirectory(undo_dir) == 0 then
  vim.fn.mkdir(undo_dir, "p")
end

-- Enable persistent undo if it's supported
if vim.fn.has("persistent_undo") == 1 then
  -- Save all undo files in a specific location
  vim.opt.undodir = undo_dir

  -- Retain up to 10,000 changes across saves and editor restarts.
  vim.opt.undolevels = 10000

  -- Actually switch on persistent undo
  vim.opt.undofile = true
end
