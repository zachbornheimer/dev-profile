-- Preview the current buffer in a browser (,B).
-- HTML: a local server whose cwd contains the file, else the file itself.
-- Markdown: markdown-preview.nvim.

local M = {}

-- GET probe timeout for "does this listener actually serve the file?"
local PROBE_TIMEOUT_MS = 300

-- Ports that listen locally but are not HTTP file servers.
local skip_ports = {
  [22] = true,
  [53] = true,
  [631] = true,
  [3306] = true,
  [5432] = true,
  [5900] = true,
  [6379] = true,
  [27017] = true,
  [11434] = true,
}

-- Known non-HTTP listeners (fast path). HTTP 2xx probe is still the gate.
local skip_commands = {
  ["Adobe Desktop Service"] = true,
  ["OneDrive Sync Service"] = true,
  ControlCenter = true,
  Dropbox = true,
  cupsd = true,
  limactl = true,
  mongod = true,
  mysqld = true,
  ollama = true,
  postgres = true,
  rapportd = true,
  ["redis-server"] = true,
  ssh = true,
  sshd = true,
}

-- Injectable HTTP probe: (url) -> boolean. Tests override; production uses curl.
M.http_ok = nil

local function run(cmd)
  local result = vim.system(cmd, { timeout = 2000, text = true }):wait()
  return result.stdout or ""
end

local function resolved(path)
  local full = vim.fn.resolve(vim.fs.normalize(path))
  if full == "/" then
    return full
  end
  return full:gsub("/+$", "")
end

local function is_local_host(host)
  return host == "*" or host == "0.0.0.0" or host == "127.0.0.1" or host == "localhost" or host == "::" or host == "::1"
end

local function parse_host_port(name)
  local host, port = name:match("^%[([^%]]+)%]:(%d+)$")
  if host then
    return host, tonumber(port)
  end
  host, port = name:match("^(.*):(%d+)$")
  if host then
    return host, tonumber(port)
  end
  return nil, nil
end

local function basename(cmd)
  return cmd:match("([^/]+)$") or cmd
end

local function is_under(dir, file)
  if dir == "/" then
    return false
  end
  if file == dir then
    return true
  end
  return vim.startswith(file, dir .. "/")
end

local function http_path(rel)
  local parts = {}
  for part in rel:gmatch("[^/]+") do
    parts[#parts + 1] = vim.uri_encode(part)
  end
  return "/" .. table.concat(parts, "/")
end

local function curl_http_ok(url)
  local max_secs = string.format("%.3f", PROBE_TIMEOUT_MS / 1000)
  local result = vim
    .system({
      "curl",
      "--silent",
      "--output",
      "/dev/null",
      "--write-out",
      "%{http_code}",
      "--location",
      "--max-time",
      max_secs,
      url,
    }, { timeout = PROBE_TIMEOUT_MS + 200, text = true })
    :wait()
  local code = tonumber((result.stdout or ""):match("%d+"))
  return code ~= nil and code >= 200 and code < 300
end

local function responds_ok(url)
  local check = M.http_ok or curl_http_ok
  return check(url)
end

local function listeners()
  local found = {}
  local pid, cmd = nil, ""
  for line in run({ "lsof", "-nP", "-w", "-iTCP", "-sTCP:LISTEN", "-F", "pcn" }):gmatch("[^\n]+") do
    local kind, value = line:match("^(%a)(.*)$")
    if kind == "p" then
      pid = value
      cmd = ""
    elseif kind == "c" then
      cmd = value
    elseif kind == "n" and pid then
      local host, port = parse_host_port(value)
      if host and port and is_local_host(host) and not skip_ports[port] and not skip_commands[basename(cmd)] then
        found[#found + 1] = { pid = pid, port = port }
      end
    end
  end
  return found
end

local function cwds_for(pids)
  if #pids == 0 then
    return {}
  end
  local by_pid = {}
  local pid
  local args = { "lsof", "-nP", "-w", "-a", "-p", table.concat(pids, ","), "-d", "cwd", "-Fn" }
  for line in run(args):gmatch("[^\n]+") do
    local kind, value = line:match("^(%a)(.*)$")
    if kind == "p" then
      pid = value
    elseif kind == "n" and pid and value ~= "" then
      by_pid[pid] = value
    end
  end
  return by_pid
end

local function candidate_urls(path)
  local found = listeners()
  local pids = {}
  for _, item in ipairs(found) do
    pids[#pids + 1] = item.pid
  end
  local cwds = cwds_for(pids)
  local candidates = {}
  for _, item in ipairs(found) do
    local dir = cwds[item.pid]
    if dir then
      dir = resolved(dir)
      if is_under(dir, path) and path ~= dir then
        local rel = path:sub(#dir + 2)
        candidates[#candidates + 1] = {
          url = "http://127.0.0.1:" .. item.port .. http_path(rel),
          depth = #dir,
        }
      end
    end
  end
  table.sort(candidates, function(a, b)
    return a.depth > b.depth
  end)
  return candidates
end

-- served_url returns a localhost URL only when a cwd-matched listener HTTP-serves path.
function M.served_url(path)
  path = resolved(path)
  for _, candidate in ipairs(candidate_urls(path)) do
    if responds_ok(candidate.url) then
      return candidate.url
    end
  end
  return nil
end

local function write_if_needed()
  if vim.bo.buftype ~= "" then
    vim.notify("Not a file buffer", vim.log.levels.WARN)
    return false
  end
  if not vim.bo.modified and vim.fn.expand("%") ~= "" then
    return true
  end
  local wrote, write_err = pcall(vim.cmd.write)
  if wrote then
    return true
  end
  vim.notify("Save the file first: " .. tostring(write_err), vim.log.levels.WARN)
  return false
end

local function open_url(url)
  local opened, open_err = vim.ui.open(url)
  if not opened then
    vim.notify("Could not open in browser: " .. tostring(open_err), vim.log.levels.ERROR)
  end
end

function M.open()
  local ft = vim.bo.filetype
  if ft == "html" then
    if not write_if_needed() then
      return
    end
    local path = vim.fn.expand("%:p")
    open_url(M.served_url(path) or path)
    return
  end
  if ft == "markdown" then
    if not write_if_needed() then
      return
    end
    vim.cmd("MarkdownPreviewToggle")
    return
  end
  vim.notify("No browser preview for " .. (ft ~= "" and ft or "this buffer"), vim.log.levels.WARN)
end

return M
