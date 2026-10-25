-- Behavior checks for this config, run against the real init.lua by test/run.sh.
-- Each scenario is one nvim process; CHECK_SCENARIO selects the startup case.
-- Any failure exits non-zero so the gate fails.

local failures = 0

local function check(name, ok, detail)
  if ok then
    print(("PASS %s"):format(name))
  else
    failures = failures + 1
    print(("FAIL %s%s"):format(name, detail and (" -- " .. tostring(detail)) or ""))
  end
end

--- Windows whose buffer belongs to snacks (picker / explorer / terminal).
local function snacks_windows()
  local found = {}
  for _, win in ipairs(vim.api.nvim_list_wins()) do
    local ft = vim.bo[vim.api.nvim_win_get_buf(win)].filetype
    if ft:match("^snacks") then
      found[#found + 1] = win
    end
  end
  return found
end

local function wait_snacks_windows()
  vim.wait(3000, function()
    return #snacks_windows() > 0
  end, 25)
  return snacks_windows()
end

local function has_normal_map(lhs)
  for _, map in ipairs(vim.api.nvim_get_keymap("n")) do
    if map.lhs == lhs then
      return true
    end
  end
  return false
end

local function close_pickers()
  for _, picker in ipairs(Snacks.picker.get()) do
    picker:close()
  end
end

--- Checks that must hold in every scenario.
local function check_config()
  check("vim_did_enter already fired", vim.v.vim_did_enter == 1, "vim_did_enter=" .. tostring(vim.v.vim_did_enter))
  check("snacks is loaded at startup", package.loaded["snacks"] ~= nil)
  check("Snacks global is available", type(Snacks) == "table")

  local modules = { "picker", "explorer", "input", "notifier", "bigfile", "quickfile", "terminal", "lazygit" }
  for _, module in ipairs(modules) do
    local config = Snacks.config[module]
    check("snacks." .. module .. " enabled", type(config) == "table" and config.enabled ~= false, vim.inspect(config))
  end

  check("explorer replaces netrw", Snacks.config.explorer.replace_netrw == true)
  check(
    "explorer does not watch the filesystem",
    Snacks.config.picker.sources.explorer.watch == false,
    "watch=" .. tostring(Snacks.config.picker.sources.explorer.watch)
  )

  -- Finder keys moved from telescope to the picker, same lhs.
  for _, lhs in ipairs({ ",ff", ",fr", ",fs", ",fc", ",ee", ",E", ",tt", ",gg", ",sn", ",T" }) do
    check("keymap " .. lhs, has_normal_map(lhs))
  end

  -- Replaced plugins must be gone, not merely unused.
  for _, name in ipairs({ "telescope", "nvim-tree", "dressing" }) do
    check("plugin " .. name .. " not loaded", package.loaded[name] == nil)
  end

  -- snacks enables its input module on UIEnter, which headless nvim never
  -- fires, so trigger the same one-shot autocmd the real UI does.
  vim.api.nvim_exec_autocmds("UIEnter", {})
  local input_source = debug.getinfo(vim.ui.input, "S").source or ""
  check("vim.ui.input owned by snacks", input_source:match("snacks") ~= nil, input_source)
  local select_source = debug.getinfo(vim.ui.select, "S").source or ""
  check("vim.ui.select owned by snacks", select_source:match("snacks") ~= nil, select_source)

  -- notifier owns vim.notify and keeps history.
  vim.notify("config-check notification", vim.log.levels.INFO, { id = "config-check" })
  local history = Snacks.notifier.get_history()
  check(
    "notifier keeps history",
    #history > 0 and vim.inspect(history):match("config%-check notification") ~= nil,
    #history .. " entries"
  )

  -- The format path must not call the removed vim.lsp.buf.formatting().
  check("vim.lsp.buf.formatting is gone in this nvim", vim.lsp.buf.formatting == nil)
  -- F must route through conform: it is the config's formatter owner (the
  -- dev-profile manifest picks the formatter per filetype). The perl/go
  -- shell-outs it replaced were a second copy of that policy.
  local f_callback
  for _, map in ipairs(vim.api.nvim_get_keymap("n")) do
    if map.lhs == "F" then
      f_callback = map.callback
    end
  end
  check("F is mapped", type(f_callback) == "function")
  local conform = require("conform")
  local real_format = conform.format
  local routed = false
  conform.format = function(...)
    routed = true
    return real_format(...)
  end
  local ok, err = pcall(f_callback)
  conform.format = real_format
  check("F formats through conform", routed and ok, err)
  check("conform owns perl formatting", conform.formatters_by_ft.perl ~= nil)
  check("conform owns go formatting", conform.formatters_by_ft.go ~= nil)
end

--- A picker opens, carries telescope's navigation keys, and closes.
local function check_picker()
  Snacks.picker.files()
  -- Items arrive asynchronously: wait for the finder to deliver some.
  vim.wait(3000, function()
    local picker = Snacks.picker.get()[1]
    return picker ~= nil and picker:count() > 0
  end, 25)
  local pickers = Snacks.picker.get()
  check("picker opens", #pickers > 0, #pickers .. " pickers")

  if #pickers > 0 then
    -- telescope hand-mapped these; they are picker defaults already
    -- (nvim normalises the key table to upper case).
    local keys = {}
    for lhs, action in pairs(pickers[1].opts.win.input.keys) do
      keys[lhs:lower()] = action
    end
    check("picker <c-j> moves down", keys["<c-j>"] ~= nil)
    check("picker <c-k> moves up", keys["<c-k>"] ~= nil)
    check("picker <c-q> sends to quickfix", keys["<c-q>"] ~= nil)
    check("picker found the fixture", pickers[1]:count() > 0, pickers[1]:count() .. " items")
  end

  close_pickers()
  check("picker closes", #Snacks.picker.get() == 0)
  check("ripgrep available for grep", vim.fn.executable("rg") == 1)
  check("fd available for file listing", vim.fn.executable("fd") == 1)
end

--- Load a lazy.nvim plugin by name and report whether it did.
local function load_plugin(name)
  local ok, err = pcall(require("lazy").load, { plugins = { name } })
  check("plugin " .. name .. " loads", ok, err)
end

local function wait_for(cond, ms)
  vim.wait(ms or 5000, cond, 25)
  return cond()
end

local function current_map(mode, lhs)
  return vim.fn.maparg(lhs, mode, false, true)
end

--- `kj` leaves insert mode without a mapping that makes `k` wait timeoutlen.
local function check_better_escape()
  check("plain insert kj map is gone", vim.fn.maparg("kj", "i") == "")
  check("plain insert lkj map is gone", vim.fn.maparg("lkj", "i") == "")
  load_plugin("better-escape.vim")
  check("better-escape owns the escape key", vim.g.better_escape_shortcut[1] == "kj")

  vim.cmd("enew!")
  vim.api.nvim_feedkeys("ikj", "tx!", false)
  check("fast kj leaves insert mode", vim.fn.mode() == "n", "mode=" .. vim.fn.mode())
  check("fast kj leaves no text behind", vim.api.nvim_get_current_line() == "", vim.api.nvim_get_current_line())

  -- Typing `k` then, past the interval, `j` must insert `j` literally.
  -- Insert mode cannot be held across feedkeys, so ask the decision function
  -- with the cursor just after a `k`.
  local function decide()
    vim.api.nvim_buf_set_lines(0, 0, -1, false, { "kx" })
    vim.api.nvim_win_set_cursor(0, { 1, 1 })
    return vim.fn["better_escape#EscapeInsertOrNot"]({ "k" }, "j")
  end
  vim.cmd("let g:better_escape_initial_press_time['k'] = reltime()")
  check("j right after k escapes", decide() == "\b\27")
  vim.cmd("let g:better_escape_initial_press_time['k'] = reltime()")
  vim.wait(vim.g.better_escape_interval + 100)
  check("j long after k is a plain j", decide() == "j")
end

--- git-conflict parses a buffer from its decoration provider, which only runs
--- on redraw, so a headless wait has to ask for one. It also raises until it
--- has parsed the buffer; -1 means "not yet".
local function conflict_count(buf)
  if package.loaded["git-conflict"] == nil then
    return -1
  end
  vim.cmd("redraw!")
  local ok, count = pcall(require("git-conflict").conflict_count, buf)
  return ok and count or -1
end

--- A real merge conflict is detected, highlighted, resolvable from <leader>m,
--- and leaves the change-commands (ct, cb, c0) alone.
local function check_git_conflict()
  local file = vim.fn.fnamemodify(vim.env.CHECK_FILE, ":p")
  wait_for(function()
    return vim.api.nvim_buf_get_name(0) == file
  end)
  local buf = vim.api.nvim_get_current_buf()
  check("editing the conflicted fixture", vim.api.nvim_buf_get_name(buf) == file, vim.api.nvim_buf_get_name(buf))
  check(
    "conflict detected",
    wait_for(function()
      return conflict_count(buf) == 1
    end),
    "no conflict found"
  )

  check("<leader>mt is a buffer-local choose-theirs map", current_map("n", ",mt").buffer == 1)
  check("<leader>mo is a buffer-local choose-ours map", current_map("n", ",mo").buffer == 1)
  check("ct is not shadowed", vim.fn.maparg("ct", "n") == "")
  check("cb is not shadowed", vim.fn.maparg("cb", "n") == "")
  check("c0 is not shadowed", vim.fn.maparg("c0", "n") == "")
  check("conflict watcher is not stopped at exit", #vim.api.nvim_get_autocmds({
    event = "VimLeavePre",
    group = "GitConflictCommands",
  }) == 0)

  vim.api.nvim_win_set_cursor(0, { 2, 0 })
  vim.cmd("normal ,mt")
  local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
  check("<leader>mt keeps the incoming side only", vim.deep_equal(lines, { "side" }), vim.inspect(lines))
  check(
    "resolved buffer has no conflicts",
    wait_for(function()
      return conflict_count(buf) == 0
    end)
  )
end

--- gx resolves plugin specs and URLs without a prompt.
local function check_gx()
  check("netrw's gx is disabled", vim.g.netrw_nogx == 1)
  check("gx is mapped in normal mode", current_map("n", "gx").desc == "Open link under cursor")
  check("gx is mapped in visual mode", current_map("x", "gx").desc == "Open link under cursor")
  load_plugin("gx.nvim")

  local opened
  require("gx.shell").execute_with_error = function(_, _, url)
    opened = url
  end
  local function browse(line, col, filetype)
    vim.cmd("enew!")
    vim.bo.filetype = filetype
    vim.api.nvim_buf_set_lines(0, 0, -1, false, { line })
    vim.api.nvim_win_set_cursor(0, { 1, col })
    opened = nil
    vim.cmd("Browse")
    return opened
  end
  local plugin_url = browse('  "folke/snacks.nvim",', 6, "lua")
  check(
    "gx on a plugin spec opens its repo",
    plugin_url == "https://github.com/folke/snacks.nvim",
    tostring(plugin_url)
  )
  local url = browse("see https://example.com/x for more", 8, "text")
  check("gx on a URL opens it", url == "https://example.com/x", tostring(url))
end

--- Quickfix opens in quicker's editable layout and the toggles work.
local function check_quicker()
  local file = vim.fn.fnamemodify(vim.env.CHECK_FILE, ":p")
  check("<leader>qq toggles quickfix", current_map("n", ",qq").desc == "Toggle quickfix")
  check("<leader>qo toggles the location list", current_map("n", ",qo").desc == "Toggle location list")
  check("<leader>ql is still persistence's", current_map("n", ",ql").desc == "Restore last session")

  vim.fn.setqflist({ { filename = file, lnum = 1, text = "hit" } })
  vim.cmd("copen")
  check(
    "quicker loads on the qf filetype",
    wait_for(function()
      return require("lazy.core.config").plugins["quicker.nvim"]._.loaded ~= nil
    end)
  )
  local function first_line()
    return vim.api.nvim_buf_get_lines(0, 0, 1, false)[1] or ""
  end
  -- The stock quickfix line is `f.txt|1| hit`; quicker drops the pipes.
  check(
    "quickfix is restyled by quicker",
    wait_for(function()
      local line = first_line()
      return line:find("hit", 1, true) ~= nil and line:find("|", 1, true) == nil
    end, 2000),
    first_line()
  )

  local function qf_open()
    return vim.fn.getqflist({ winid = 0 }).winid ~= 0
  end
  check("quickfix is open", qf_open())
  current_map("n", ",qq").callback()
  check("<leader>qq closes it", not qf_open())
  current_map("n", ",qq").callback()
  check("<leader>qq opens it again", qf_open())
end

--- `;` opens a floating input, submitting runs the command, `:` stays native.
local function check_fine_cmdline()
  check("; opens the floating command line", current_map("n", ";").desc == "Floating command line")
  check(": stays the native command line", vim.fn.maparg(":", "n") == "")

  vim.g.fine_ran = nil
  vim.cmd("FineCmdline")
  local input = require("fine-cmdline").input
  check("input is mounted", input ~= nil and vim.api.nvim_buf_is_valid(input.bufnr))
  -- nui takes focus and enters insert mode from a scheduled BufWinEnter hook.
  check(
    "input takes focus",
    wait_for(function()
      return vim.api.nvim_get_current_win() == input.winid
    end, 2000)
  )
  local floating = vim.api.nvim_win_get_config(input.winid).relative ~= ""
  check("input is a floating window", floating)
  check("input is a prompt buffer", vim.bo[input.bufnr].buftype == "prompt")
  input.input_props.on_submit("let g:fine_ran = 42")
  -- nui runs the callback after it has unmounted the input, not inside on_submit.
  check(
    "submitting runs the command",
    wait_for(function()
      return vim.g.fine_ran == 42
    end, 2000),
    tostring(vim.g.fine_ran)
  )
  check(
    "submitted command lands in history",
    vim.fn.histget("cmd", -1) == "let g:fine_ran = 42",
    vim.fn.histget("cmd", -1)
  )
  input:unmount()
end

--- The annotation half of herdr-nvim exists only inside a herdr pane.
local function check_herdr(inside)
  local where = inside and "inside herdr" or "outside herdr"
  check(
    "herdr-nvim is " .. (inside and "enabled" or "disabled") .. " " .. where,
    (require("lazy.core.config").plugins["herdr-nvim"] ~= nil) == inside
  )
  pcall(require("lazy").load, { plugins = { "herdr-nvim" } })
  check(":Herdr is " .. (inside and "registered" or "absent") .. " " .. where, (vim.fn.exists(":Herdr") == 2) == inside)
  check(
    "<leader>ac is " .. (inside and "mapped" or "unmapped") .. " " .. where,
    (current_map("n", ",ac").desc ~= nil) == inside
  )
end

local function check_plugins(inside_herdr)
  local declared = require("lazy.core.config").plugins
  for _, name in ipairs({ "gx.nvim", "git-conflict.nvim", "better-escape.vim", "quicker.nvim", "fine-cmdline.nvim" }) do
    check("plugin " .. name .. " is declared", declared[name] ~= nil)
  end
  check_herdr(inside_herdr)
  if inside_herdr then
    -- The conflict check needs the buffer the nvim was launched with; later
    -- checks open scratch buffers.
    check_git_conflict()
    check_better_escape()
    check_gx()
    check_quicker()
    check_fine_cmdline()
  end
end

--- WCAG contrast ratio, computed here rather than borrowed from the config.
local function contrast_ratio(a, b)
  local function linear(c8)
    local c = c8 / 255
    return c <= 0.03928 and c / 12.92 or ((c + 0.055) / 1.055) ^ 2.4
  end
  local function luminance(rgb)
    return 0.2126 * linear(math.floor(rgb / 0x10000) % 0x100)
      + 0.7152 * linear(math.floor(rgb / 0x100) % 0x100)
      + 0.0722 * linear(rgb % 0x100)
  end
  local la, lb = luminance(a), luminance(b)
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05)
end

--- Text groups under WCAG AA (4.5:1) on the background they are drawn on.
local function unreadable_groups()
  local exempt = require("zach.core.contrast").exempt
  local normal_bg = vim.api.nvim_get_hl(0, { name = "Normal" }).bg
  local failing = {}
  for name, hl in pairs(vim.api.nvim_get_hl(0, {})) do
    local bg = hl.bg or normal_bg
    if hl.fg and bg and not hl.link and not hl.reverse and not exempt(name, hl.fg, bg) then
      local ratio = contrast_ratio(hl.fg, bg)
      if ratio < 4.5 then
        failing[#failing + 1] = ("%s %.2f"):format(name, ratio)
      end
    end
  end
  table.sort(failing)
  return failing
end

--- The editor follows macOS appearance the way kitty does, paints kitty's
--- background opaquely, and keeps every text group readable on it.
local function check_colors()
  local failing = unreadable_groups()
  check("startup: every text group reaches 4.5:1", #failing == 0, table.concat(failing, ", "))
  -- Lazy-loaded plugins define their highlights long after the colorscheme.
  local lazy_plugins = {}
  for name, plugin in pairs(require("lazy.core.config").plugins) do
    if not plugin._.loaded then
      lazy_plugins[#lazy_plugins + 1] = name
    end
  end
  pcall(require("lazy").load, { plugins = lazy_plugins })
  failing = unreadable_groups()
  check("after lazy loads: every text group reaches 4.5:1", #failing == 0, table.concat(failing, ", "))

  local appearance = require("zach.core.appearance")
  local real = appearance.preferred_background
  for _, case in ipairs({
    { appearance = "dark", base = 0x232136 }, -- Rosé Pine Moon: kitty dark-theme.auto.conf
    { appearance = "light", base = 0xfaf4ed }, -- Rosé Pine Dawn: kitty light-theme.auto.conf
  }) do
    appearance.preferred_background = function()
      return case.appearance
    end
    vim.api.nvim_exec_autocmds("FocusGained", {})
    local bg = vim.api.nvim_get_hl(0, { name = "Normal" }).bg
    check(case.appearance .. ": background follows macOS", vim.o.background == case.appearance, vim.o.background)
    check(
      case.appearance .. ": Normal paints kitty's background",
      bg == case.base,
      bg and ("#%06x"):format(bg) or "transparent"
    )
    local failing = unreadable_groups()
    check(case.appearance .. ": every text group reaches 4.5:1", #failing == 0, table.concat(failing, ", "))
  end
  appearance.preferred_background = real
end

local scenario = vim.env.CHECK_SCENARIO or "config"

if scenario == "config" then
  check_config()
  check_picker()
end

if scenario == "colors" then
  check_colors()
end

if scenario == "plugins" then
  check_plugins(true)
end

if scenario == "no-herdr" then
  check_plugins(false)
end

if scenario == "bigfile" then
  check("bigfile filetype on a 2MB buffer", vim.bo.filetype == "bigfile", "filetype=" .. vim.bo.filetype)
  check("bigfile disables completion", vim.b.completion == false)
end

if scenario == "file" then
  check_config()
  local expected = vim.fn.fnamemodify(vim.env.CHECK_FILE, ":p")
  check("explorer opened for a launched file", #wait_snacks_windows() > 0)
  check(
    "focus stays in the editor",
    vim.api.nvim_buf_get_name(0) == expected,
    vim.api.nvim_buf_get_name(0) .. " != " .. expected
  )
  check(
    "explorer can be toggled closed",
    (function()
      require("zach.core.explorer").toggle()
      vim.wait(3000, function()
        return #Snacks.picker.get() == 0
      end, 25)
      return #Snacks.picker.get() == 0
    end)()
  )
  check(
    "explorer can be revealed again",
    (function()
      require("zach.core.explorer").reveal()
      vim.wait(3000, function()
        return #Snacks.picker.get({ source = "explorer" }) > 0
      end, 25)
      return #Snacks.picker.get({ source = "explorer" }) > 0
    end)()
  )
end

for _, quiet in ipairs({ "gitcommit", "home", "stdin", "oneshot" }) do
  if scenario == quiet then
    check("no explorer for a " .. quiet .. " launch", #snacks_windows() == 0, #snacks_windows() .. " snacks windows")
  end
end
if scenario == "uvscript" or scenario == "envft" then
  check("filetype is python", vim.bo.filetype == "python", "filetype=" .. vim.bo.filetype)
  check("syntax follows filetype", vim.bo.syntax == "python", "syntax=" .. vim.bo.syntax)
end

if scenario == "directory" then
  check("explorer replaces netrw for `nvim <dir>`", #wait_snacks_windows() > 0)
end

if failures > 0 then
  print(("FAILED %d check(s) in scenario %s"):format(failures, scenario))
  vim.cmd("cquit 1")
end
print(("ok scenario %s"):format(scenario))
vim.cmd("qall!")
