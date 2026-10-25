-- leader key (also read by every plugin spec's `keys`, so it must be set first)
vim.g.mapleader = ","

local keymap = vim.keymap -- for conciseness

---------------------
-- General Keymaps -------------------

-- clear search highlights
keymap.set("n", "<leader><Backspace>", ":nohl<CR>", { desc = "Clear search highlights" })

-- delete single character without copying into register
-- keymap.set("n", "x", '"_x')

-- save all files
keymap.set("n", "W", ":wa<CR>", { desc = "W to save all open files" })

-- force sudo save
keymap.set("n", "w!!", ":w !sudo tee > /dev/null % <CR>", { desc = "W to save all open files" })

-- window management
keymap.set("n", "<leader>vw", "<C-w>v", { desc = "Split window vertically" }) -- split window vertically
keymap.set("n", "<leader>hw", "<C-w>s", { desc = "Split window horizontally" }) -- split window horizontally
keymap.set("n", "<leader>ew", "<C-w>=", { desc = "Make splits equal size" }) -- make split windows equal width & height
keymap.set("n", "<leader>ww", "<cmd>close<CR>", { desc = "Close current split" }) -- close current split window

keymap.set("n", "<leader>%", ":source %<CR>", { desc = "Source the current file" })

keymap.set("n", "<leader>to", "<cmd>tabnew<CR>", { desc = "Open new tab" }) -- open new tab
keymap.set("n", "<leader>tx", "<cmd>tabclose<CR>", { desc = "Close current tab" }) -- close current tab
keymap.set("n", "<leader>tn", "<cmd>tabn<CR>", { desc = "Go to next tab" }) --  go to next tab
keymap.set("n", "<leader>tp", "<cmd>tabp<CR>", { desc = "Go to previous tab" }) --  go to previous tab
keymap.set("n", "<leader>tf", "<cmd>tabnew %<CR>", { desc = "Open current buffer in new tab" }) --  move current buffer to new tab

-- shebangs + code shortcuts

vim.cmd("iab hbs #! /bin/sh<CR><BS><CR>")
vim.cmd("iab hbp #! /usr/bin/env perl<CR>use strict;<CR>use warnings;<CR>use feature 'say';<CR><BS><CR>")
vim.cmd("iab hb6 #! /usr/bin/env perl6<CR>use v6;<CR><BS><CR>")
vim.cmd("iab phpse ini_set('display_errors', 1); ini_set('display_startup_errors', 1); error_reporting(E_ALL);<CR>")
vim.cmd("iab udd use Data::Dumper;<CR>print Dumper")

-- Make <Ctrl-Z> or :stop save all open docs
keymap.set("n", "<C-z>", ":wa<CR>:stop<CR>", { desc = "Save all open docs and stop vim" })
keymap.set("n", "zz", ":wa<CR>:stop<CR>", { desc = "Save all open docs and stop vim" })

-- ToggleAlternates
keymap.set("n", "<leader>!", ":ToggleAlternate<CR>", { desc = "Run the ToggleAlternate plugin" })

-- Useful shortcuts
keymap.set("n", "<leader>x", ":!chmod +x %<CR>", { desc = "Make the current file executable" })

-- Trash the file on disk. No and Esc only dismiss the prompt. The window stays open.
local TRASH_PROGRAM = "trash"
local CONFIRM_YES = 1
local CONFIRM_DEFAULT_NO = 2

local function trash_current_file()
  local name = vim.api.nvim_buf_get_name(0)
  local abspath = name ~= "" and vim.fn.fnamemodify(name, ":p") or ""
  local kind = abspath ~= "" and vim.fn.getftype(abspath) or ""
  if abspath == "" or vim.bo.buftype ~= "" or (kind ~= "file" and kind ~= "link") then
    vim.api.nvim_echo({ { "No file to trash", "WarningMsg" } }, false, {})
    return
  end
  local choice = vim.fn.confirm("Delete " .. abspath .. "?", "&Yes\n&No", CONFIRM_DEFAULT_NO)
  if choice ~= CONFIRM_YES then
    return
  end
  local ok, result = pcall(function()
    return vim.system({ TRASH_PROGRAM, abspath }, { text = true }):wait()
  end)
  local detail = ""
  if ok and result then
    detail = vim.trim((result.stderr or "") ~= "" and result.stderr or (result.stdout or ""))
  elseif not ok then
    detail = tostring(result)
  end
  if not ok or not result or result.code ~= 0 or vim.fn.filereadable(abspath) == 1 then
    if detail == "" then
      detail = "exit " .. tostring(result and result.code)
    end
    vim.api.nvim_echo({ { "trash failed: " .. detail, "ErrorMsg" } }, true, {})
    return
  end
  vim.wo.statusline = ("Successfully trashed " .. abspath):gsub("%%", "%%%%")
  vim.cmd("redrawstatus")
end

keymap.set("n", "<leader>D", trash_current_file, { desc = "Trash the current file" })

keymap.set("n", "<leader>cx", 'mzggVG"+y`z', {
  desc = "Copy entire buffer to clipboard",
})
keymap.set("x", "<leader>cx", '"+y', {
  desc = "Copy selection to system clipboard",
})
keymap.set("n", "<leader>c%", ':let @+ = expand("%:p")<CR>', {
  desc = "Copy current file's absolute path to clipboard",
})
keymap.set("n", "<leader>cp", '"+p', {
  desc = "Paste from system clipboard",
})
keymap.set("x", "<leader>cp", '"+p', {
  desc = "Paste from system clipboard",
})

-- Replace selection (or whole buffer if nothing selected) with system clipboard
keymap.set("x", "<leader>crx", '"_d"+P', {
  desc = "Replace selection with system clipboard",
})
keymap.set("n", "<leader>crx", 'ggVG"_d"+P', {
  desc = "Replace entire buffer with system clipboard",
})

-- Toggle the file explorer with <leader>T (alias of <leader>ee).
vim.keymap.set("n", "<leader>T", require("zach.core.explorer").toggle, {
  desc = "Toggle file explorer",
})

keymap.set("n", "<leader>B", require("zach.core.preview").open, { desc = "Preview in browser" })

-- Toggle soft wrap (word-aware via linebreak) with <leader>tw.
vim.keymap.set("n", "<leader>tw", function()
  vim.opt.wrap = not vim.opt.wrap:get()
end, {
  desc = "Toggle soft wrap (word-aware)",
})

-- Function to run the current file based on the shebang
local function run_with_shebang()
  local filename = vim.fn.expand("%") -- Get current file name
  local first_line = vim.fn.getline(1) -- Get the first line (shebang)

  -- Check if it's a Perl file based on extension or shebang
  if filename:match("%.pl$") or first_line:match("^#!/usr/bin/perl") then
    -- Run Perl file with -I. flag
    vim.cmd("!perl -I. " .. vim.fn.shellescape(filename))
  elseif filename:match("%.go$") then
    vim.cmd("!go run " .. vim.fn.shellescape(filename))
  elseif first_line:match("^#!") then
    -- Extract interpreter from the shebang (excluding the "#!" part)
    local interpreter = first_line:sub(3)
    -- Run the file with the interpreter from the shebang
    vim.cmd("!" .. interpreter .. " " .. vim.fn.shellescape(filename))
  else
    print("No valid shebang or not a Perl file.")
  end
end

-- Formatting is owned by conform (plugins/coding/conform.lua): the dev-profile
-- manifest decides the formatter per filetype, with LSP as its fallback. The
-- perl/go shell-outs that used to live here were a second copy of that policy.
keymap.set("n", "F", function()
  require("conform").format({ async = true, lsp_format = "fallback" })
end, { desc = "Format buffer with conform (LSP fallback)" })

-- zq (Zach Quality) Integrations
vim.keymap.set("n", "<leader>qf", ":!zq fix<CR>", { desc = "Run zq fix (Personal/Work)" })
vim.keymap.set("n", "<leader>qc", ":!zq check<CR>", { desc = "Run zq check (Personal/Work)" })
vim.keymap.set("n", "<leader>qa", ":!zq audit<CR>", { desc = "Run zq audit (Personal/Work)" })

vim.keymap.set("n", "<C-s>", ":w<CR>", { desc = "Save file" })
vim.keymap.set("n", "<C-q>", ":qa<CR>", { desc = "Quit" })

-- Check whether the current buffer has a filepath.
local function has_filepath()
  return vim.api.nvim_buf_get_name(0) ~= ""
end

-- Insert mode: Escape to normal mode, saving named files.
vim.keymap.set("i", "<Esc>", function()
  return has_filepath() and "<Esc><Cmd>update<CR>" or "<Esc>"
end, { expr = true, desc = "Exit insert mode and save" })

vim.keymap.set("n", "<C-8>", 'viw"-y:%s/<C-r>-/<C-r>-/g<Left><Left>')
vim.keymap.set("v", "<C-8>", '"-y:%s/<C-r>-/<C-r>-/g<Left><Left>')
