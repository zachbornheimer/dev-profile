-- Persistent undo that survives a path becoming a symlink, and that is not
-- thrown away when something else rewrites the file.
--
-- Nvim names the undo file from the resolved path, and refuses to load it when
-- the file's hash no longer matches ("File contents changed, cannot use undo
-- info"). Two things follow:
--
--   * History written before ~/.agents, ~/.config/nvim and the other dotfile
--     links pointed into this repo is stored under the old path. If the bytes
--     still match, copy that file to the resolved name before Nvim looks, so
--     `u` finds it.
--   * A mismatch cannot be applied: the stored edits are line ranges against
--     the old text, and replaying them corrupts the buffer. Move that file
--     aside before the next :w replaces it with an empty history. :UndoArchive
--     opens the newest full snapshot read-only.

local M = {}

local UNDO_DIR = vim.fn.expand("$HOME") .. "/.VIM_UNDO_FILES"
local MAGIC = "Vim\x9fUnDo\xe5"
local UH_MAGIC = "\x5f\xd0"
local UE_MAGIC = "\xf5\x18"
local HASH_BYTES = 32
-- Header is magic (9) + version (2) + hash (32).
local HASH_AT = 12
local MAX_HASH_BYTES = 8 * 1024 * 1024

local links ---@type {from: string, to: string}[]|nil

local function trim_slash(path)
  if path == "/" then
    return path
  end
  return (path:gsub("/+$", ""))
end

local function undo_name(dir, path)
  return dir .. "/" .. trim_slash(path):gsub("/", "%%")
end

--- sha256 Nvim stores: each line, without its newline, followed by a NUL.
---@param path string
---@return string|nil hex
local function content_hash(path)
  local stat = vim.uv.fs_stat(path)
  if not stat or stat.type ~= "file" or stat.size > MAX_HASH_BYTES then
    return nil
  end
  local lines = vim.fn.readfile(path)
  if #lines == 0 then
    return nil
  end
  return vim.fn.sha256(table.concat(lines, "\0") .. "\0")
end

---@param undo_path string
---@return string|nil hex
local function undo_hash_hex(undo_path)
  local fd = vim.uv.fs_open(undo_path, "r", 438)
  if not fd then
    return nil
  end
  local data = vim.uv.fs_read(fd, HASH_AT + HASH_BYTES - 1, 0)
  vim.uv.fs_close(fd)
  if type(data) ~= "string" or #data < HASH_AT + HASH_BYTES - 1 or data:sub(1, #MAGIC) ~= MAGIC then
    return nil
  end
  return (
    data:sub(HASH_AT, HASH_AT + HASH_BYTES - 1):gsub(".", function(c)
      return string.format("%02x", c:byte())
    end)
  )
end

local function consider_link(path, out)
  local stat = vim.uv.fs_lstat(path)
  if not stat or stat.type ~= "link" then
    return
  end
  local target = trim_slash(vim.fn.resolve(path))
  local from = trim_slash(path)
  if target ~= "" and target ~= from then
    out[#out + 1] = { from = from, to = target }
  end
end

local function symlink_children(dir, out)
  local handle = vim.uv.fs_opendir(dir, nil, 256)
  if not handle then
    return
  end
  while true do
    local entries = vim.uv.fs_readdir(handle)
    if not entries then
      break
    end
    for _, ent in ipairs(entries) do
      if ent.type == "link" then
        consider_link(dir .. "/" .. ent.name, out)
      end
    end
  end
  vim.uv.fs_closedir(handle)
end

--- Live symlinks whose targets are where Nvim now resolves a file.
--- $HOME and $HOME/.config cover the dotfile cutover; one extra level covers
--- links like ~/.grok/skills that are not themselves the link.
local function symlink_links()
  if links then
    return links
  end
  local found = {}
  local home = vim.env.HOME
  if not home or home == "" then
    links = found
    return found
  end
  symlink_children(home, found)
  local config = home .. "/.config"
  symlink_children(config, found)
  for _, dir in ipairs({ home .. "/.grok", home .. "/.claude", home .. "/.codex", home .. "/.vim" }) do
    local stat = vim.uv.fs_lstat(dir)
    if stat and stat.type == "directory" then
      symlink_children(dir, found)
    end
  end
  links = found
  return found
end

--- Undo files recorded under a symlink path that resolves to `resolved`.
---@param resolved string
---@return string[]
local function alias_undo_paths(dir, resolved)
  local found = {}
  resolved = trim_slash(resolved)
  for _, link in ipairs(symlink_links()) do
    local alias
    if resolved == link.to then
      alias = link.from
    elseif vim.startswith(resolved, link.to .. "/") then
      alias = link.from .. resolved:sub(#link.to + 1)
    end
    if alias then
      local name = undo_name(dir, alias)
      if vim.uv.fs_stat(name) then
        found[#found + 1] = name
      end
    end
  end
  return found
end

local function u32(data, at)
  local a, b, c, d = data:byte(at, at + 3)
  if not a then
    return nil
  end
  return a * 16777216 + b * 65536 + c * 256 + d
end

--- Lines of the newest full-file snapshot in an undo file, or nil.
---@param undo_path string
---@return string[]|nil
---@return integer|nil seq
function M.snapshot(undo_path)
  local fd = vim.uv.fs_open(undo_path, "r", 438)
  if not fd then
    return nil
  end
  local stat = vim.uv.fs_fstat(fd)
  local data = stat and vim.uv.fs_read(fd, stat.size, 0) or nil
  vim.uv.fs_close(fd)
  if type(data) ~= "string" or data:sub(1, #MAGIC) ~= MAGIC then
    return nil
  end

  local best_seq, best_lines = -1, nil
  local start = 1
  while true do
    local uh = data:find(UH_MAGIC, start, true)
    if not uh then
      break
    end
    local seq = u32(data, uh + 18)
    local ue = data:find(UE_MAGIC, uh + 2, true)
    if seq and ue and ue < uh + 800 then
      local size = u32(data, ue + 14)
      local pos = ue + 18
      local lines = {}
      local ok = size ~= nil and size > 0 and size < 200000
      if ok then
        for _ = 1, size do
          local len = u32(data, pos)
          if not len or pos + 3 + len > #data then
            ok = false
            break
          end
          lines[#lines + 1] = data:sub(pos + 4, pos + 3 + len)
          pos = pos + 4 + len
        end
      end
      if ok and seq > best_seq then
        best_seq = seq
        best_lines = lines
      end
    end
    start = uh + 2
  end
  return best_lines, best_seq > -1 and best_seq or nil
end

--- Copy a still-valid alias history onto the resolved path, and park a
--- mismatched history where the next write cannot replace it.
---@param dir string
---@param resolved string
---@return string|nil parked path of history that does not match, when one exists
function M.prepare(dir, resolved)
  resolved = trim_slash(resolved)
  if vim.fn.filereadable(resolved) ~= 1 then
    return nil
  end
  local file_hash = content_hash(resolved)
  if not file_hash then
    return nil
  end
  local canonical = undo_name(dir, resolved)
  local canonical_hash = undo_hash_hex(canonical)
  local parked = nil
  -- A mismatch at the resolved name will be replaced on the next write.
  -- Park it first so a still-valid alias can take the name.
  if canonical_hash and canonical_hash ~= file_hash and vim.uv.fs_stat(canonical) then
    local mtime = vim.uv.fs_stat(canonical).mtime.sec
    local dest = canonical .. ".archive-" .. os.date("%Y%m%dT%H%M%SZ", mtime)
    if not vim.uv.fs_stat(dest) then
      vim.uv.fs_rename(canonical, dest)
    end
    parked = dest
    canonical_hash = nil
  end
  if canonical_hash == file_hash then
    for _, alias in ipairs(alias_undo_paths(dir, resolved)) do
      if alias ~= canonical and undo_hash_hex(alias) ~= file_hash then
        return alias
      end
    end
    return nil
  end
  for _, alias in ipairs(alias_undo_paths(dir, resolved)) do
    if alias ~= canonical and undo_hash_hex(alias) == file_hash and not vim.uv.fs_stat(canonical) then
      vim.uv.fs_copyfile(alias, canonical, 0)
      return nil
    elseif alias ~= canonical and not parked then
      parked = alias
    end
  end
  return parked
end

local function open_archive(undo_path)
  local lines, seq = M.snapshot(undo_path)
  if not lines then
    vim.api.nvim_echo({ { "Undo archive is not a full snapshot: " .. undo_path, "WarningMsg" } }, false, {})
    return
  end
  local when = os.date("%Y-%m-%d %H:%M", vim.uv.fs_stat(undo_path).mtime.sec)
  local filetype = vim.bo.filetype
  vim.cmd("split")
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_win_set_buf(0, buf)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].buftype = "nofile"
  vim.bo[buf].bufhidden = "wipe"
  vim.bo[buf].swapfile = false
  vim.bo[buf].modifiable = false
  vim.bo[buf].filetype = filetype
  pcall(vim.api.nvim_buf_set_name, buf, undo_path .. ".snapshot")
end

local function archives_for(dir, resolved, parked)
  local found = {}
  if parked and vim.uv.fs_stat(parked) then
    found[#found + 1] = parked
  end
  for _, alias in ipairs(alias_undo_paths(dir, resolved)) do
    found[#found + 1] = alias
  end
  local prefix = undo_name(dir, resolved) .. ".archive-"
  local handle = vim.uv.fs_opendir(dir, nil, 256)
  if handle then
    while true do
      local entries = vim.uv.fs_readdir(handle)
      if not entries then
        break
      end
      for _, ent in ipairs(entries) do
        local path = dir .. "/" .. ent.name
        if path:sub(1, #prefix) == prefix then
          found[#found + 1] = path
        end
      end
    end
    vim.uv.fs_closedir(handle)
  end
  return found
end

function M.setup()
  if vim.fn.isdirectory(UNDO_DIR) == 0 then
    vim.fn.mkdir(UNDO_DIR, "p")
  end
  if vim.fn.has("persistent_undo") ~= 1 then
    return
  end
  vim.opt.undodir = UNDO_DIR
  vim.opt.undolevels = 10000
  vim.opt.undofile = true

  local group = vim.api.nvim_create_augroup("zach_undo", { clear = true })

  -- Before Nvim reads the undo file. A match copied here is the file it loads.
  vim.api.nvim_create_autocmd("BufReadPre", {
    group = group,
    callback = function(ev)
      local name = vim.api.nvim_buf_get_name(ev.buf)
      if name == "" or vim.bo[ev.buf].buftype ~= "" then
        return
      end
      local resolved = trim_slash(vim.fn.resolve(name))
      local parked = M.prepare(UNDO_DIR, resolved)
      if parked then
        vim.b[ev.buf].undo_archive = parked
      end
    end,
  })

  vim.api.nvim_create_autocmd("BufReadPost", {
    group = group,
    callback = function(ev)
      local parked = vim.b[ev.buf].undo_archive
      if not parked or not vim.uv.fs_stat(parked) then
        return
      end
      local when = os.date("%Y-%m-%d", vim.uv.fs_stat(parked).mtime.sec)
      local msg = vim.fn.undotree().seq_last == 0
          and ("No undo: history from %s does not match this file (edited outside nvim). :UndoArchive"):format(when)
        or ("Older undo from %s does not match this file (edited outside nvim). :UndoArchive"):format(when)
      vim.schedule(function()
        if not vim.api.nvim_buf_is_valid(ev.buf) then
          return
        end
        vim.api.nvim_echo({ { msg, "WarningMsg" } }, false, {})
      end)
    end,
  })

  vim.api.nvim_create_user_command("UndoArchive", function()
    local name = vim.api.nvim_buf_get_name(0)
    if name == "" then
      vim.api.nvim_echo({ { "No file", "WarningMsg" } }, false, {})
      return
    end
    local resolved = trim_slash(vim.fn.resolve(name))
    local found = archives_for(UNDO_DIR, resolved, vim.b.undo_archive)
    if #found == 0 then
      vim.api.nvim_echo({ { "No parked undo history for this file", "WarningMsg" } }, false, {})
      return
    end
    table.sort(found, function(a, b)
      return vim.uv.fs_stat(a).mtime.sec > vim.uv.fs_stat(b).mtime.sec
    end)
    open_archive(found[1])
  end, { desc = "Open the newest parked undo snapshot read-only" })
end

M.content_hash = content_hash
M.undo_hash_hex = undo_hash_hex
M.undo_name = undo_name

return M
