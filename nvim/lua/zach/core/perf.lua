-- Always-on session timing → JSONL under stdpath("log")/perf.jsonl
-- Loaded first from init.lua so the autocmd wrap sees later registrations.
-- Convention: ms = this row's duration; session_ms = age since enter/load.

local M = {}

local MAX_LOG_BYTES = 2 * 1024 * 1024
local DEFAULT_THRESHOLD_MS = 50
local TAIL_LINES = 50
local CMD_NAME = "NvimPerf"
local CMD_DESC = "Open the nvim session performance log"
local SCRATCH_TITLE = "nvim-perf"
local EMPTY_LOG_MSG = "-- perf log empty or unreadable --"

local load_ns = vim.uv.hrtime()
local enter_ns ---@type number|nil
local leave_pre_ns ---@type number|nil

local function threshold_ms()
  local raw = vim.env.NVIM_PERF_THRESHOLD_MS
  if raw == nil or raw == "" then
    return DEFAULT_THRESHOLD_MS
  end
  local n = tonumber(raw)
  if n == nil or n < 0 then
    return DEFAULT_THRESHOLD_MS
  end
  return n
end

local function log_path()
  local override = vim.env.NVIM_PERF_LOG
  if override ~= nil and override ~= "" then
    return override
  end
  return vim.fn.stdpath("log") .. "/perf.jsonl"
end

local function now_ts()
  return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

local function ms_since(start_ns)
  return (vim.uv.hrtime() - start_ns) / 1e6
end

local function session_age_ms()
  if enter_ns then
    return ms_since(enter_ns)
  end
  return ms_since(load_ns)
end

local function nvim_version()
  local v = vim.version()
  return string.format("%d.%d.%d", v.major, v.minor, v.patch)
end

---@param path string
local function rotate_if_needed(path)
  local stat = vim.uv.fs_stat(path)
  if not stat or not stat.size or stat.size <= MAX_LOG_BYTES then
    return
  end
  vim.uv.fs_rename(path, path .. ".1")
end

---@param row table
local function append_row(row)
  pcall(function()
    local path = log_path()
    vim.fn.mkdir(vim.fn.fnamemodify(path, ":h"), "p")
    rotate_if_needed(path)
    local line = vim.json.encode(row) .. "\n"
    local f = io.open(path, "a")
    if not f then
      return
    end
    f:write(line)
    f:close()
  end)
end

function M.append(row)
  append_row(row)
end

--- Time fn and always append {event="span", name, ms, ts, ...extra}. Returns fn results.
---@param name string
---@param fn function
---@param extra table|nil
function M.span(name, fn, extra)
  local t0 = vim.uv.hrtime()
  local results = { pcall(fn) }
  local ms = ms_since(t0)
  local row = {
    event = "span",
    name = name,
    ms = ms,
    ts = now_ts(),
  }
  if type(extra) == "table" then
    for k, v in pairs(extra) do
      row[k] = v
    end
  end
  append_row(row)
  local ok = results[1]
  if not ok then
    error(results[2], 0)
  end
  return (table.unpack or unpack)(results, 2)
end

local function copy_opts(opts)
  local out = {}
  for k, v in pairs(opts) do
    out[k] = v
  end
  return out
end

local function event_name(event)
  if type(event) == "table" then
    return table.concat(event, ",")
  end
  return tostring(event)
end

local orig_create_autocmd = vim.api.nvim_create_autocmd

vim.api.nvim_create_autocmd = function(event, opts)
  opts = copy_opts(opts or {})
  local cb = opts.callback
  if type(cb) == "function" then
    local name = event_name(event)
    local desc = opts.desc
    -- Capture at wrap time: many plugins omit opts.desc.
    local info = debug.getinfo(cb, "S")
    local src = info and info.source or nil
    local line = info and info.linedefined or nil
    opts.callback = function(...)
      local t0 = vim.uv.hrtime()
      local ok, result = pcall(cb, ...)
      local ms = ms_since(t0)
      if ms >= threshold_ms() then
        local ev = ...
        local file ---@type string|nil
        if type(ev) == "table" then
          file = ev.file
          if (file == nil or file == "") and type(ev.buf) == "number" then
            local ok_name, bufname = pcall(vim.api.nvim_buf_get_name, ev.buf)
            if ok_name and bufname ~= "" then
              file = bufname
            end
          end
        end
        append_row({
          event = "autocmd",
          name = name,
          desc = desc,
          src = src,
          line = line,
          file = file,
          ms = ms,
          ts = now_ts(),
        })
      end
      if not ok then
        error(result, 0)
      end
      return result
    end
  end
  return orig_create_autocmd(event, opts)
end

append_row({
  event = "session_start",
  ts = now_ts(),
  pid = vim.fn.getpid(),
  version = nvim_version(),
  cwd = vim.fn.getcwd(),
})

orig_create_autocmd("VimEnter", {
  desc = "perf: record VimEnter timing",
  callback = function()
    enter_ns = vim.uv.hrtime()
    local ms = ms_since(load_ns)
    append_row({
      event = "vim_enter",
      ts = now_ts(),
      ms = ms,
      session_ms = ms,
    })
  end,
})

orig_create_autocmd("VimLeavePre", {
  desc = "perf: record VimLeavePre timing",
  callback = function()
    local t0 = vim.uv.hrtime()
    leave_pre_ns = t0
    local clients = 0
    pcall(function()
      clients = #vim.lsp.get_clients()
    end)
    local age = session_age_ms()
    local ms = ms_since(t0)
    append_row({
      event = "vim_leave_pre",
      ts = now_ts(),
      ms = ms,
      session_ms = age,
      client_count = clients,
      buf_count = #vim.api.nvim_list_bufs(),
    })
  end,
})

orig_create_autocmd("VimLeave", {
  desc = "perf: record VimLeave timing",
  callback = function()
    local since_pre = leave_pre_ns and ms_since(leave_pre_ns) or 0
    append_row({
      event = "vim_leave",
      ts = now_ts(),
      ms = since_pre,
      session_ms = session_age_ms(),
    })
  end,
})

if vim.env.NVIM_PROF ~= nil and vim.env.NVIM_PROF ~= "" then
  local stamp = os.date("%Y%m%d-%H%M%S")
  local profile_path = vim.fn.stdpath("log") .. "/profile-" .. stamp .. ".log"
  pcall(function()
    vim.fn.mkdir(vim.fn.stdpath("log"), "p")
    vim.cmd("profile start " .. vim.fn.fnameescape(profile_path))
    vim.cmd("profile func *")
    vim.cmd("profile file *")
  end)
  orig_create_autocmd("VimLeavePre", {
    desc = "perf: stop stdlib profile dump",
    callback = function()
      pcall(vim.cmd, "profile stop")
    end,
  })
end

local function read_tail(path, n)
  local f = io.open(path, "r")
  if not f then
    return { EMPTY_LOG_MSG }
  end
  local lines = {}
  for line in f:lines() do
    lines[#lines + 1] = line
  end
  f:close()
  if #lines == 0 then
    return { EMPTY_LOG_MSG }
  end
  if #lines <= n then
    return lines
  end
  local out = {}
  for i = #lines - n + 1, #lines do
    out[#out + 1] = lines[i]
  end
  return out
end

vim.api.nvim_create_user_command(CMD_NAME, function()
  local path = log_path()
  local lines = read_tail(path, TAIL_LINES)
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_name(buf, SCRATCH_TITLE)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false
  vim.bo[buf].bufhidden = "wipe"
  vim.bo[buf].filetype = "json"
  vim.api.nvim_set_current_buf(buf)
end, { desc = CMD_DESC })

return M
