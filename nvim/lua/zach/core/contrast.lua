-- Keep every highlight readable, whatever the colorscheme ships.
-- Text must reach MIN_CONTRAST (WCAG AA, 4.5:1) against its own background,
-- or Normal's when it has none. Decoration that is meant to recede (indent
-- guides, borders, fill characters) and text hidden on purpose (fg == bg)
-- are left alone. The cursor must reach the
-- ratio against every background it can sit on (Normal, Visual, CursorLine),
-- and the text under a block cursor against the cursor.

local M = {}

local MIN_CONTRAST = 4.5
local LERP_STEP = 0.02
local BLACK = 0x000000
local WHITE = 0xFFFFFF
local GUICURSOR = table.concat({
  "n-v-c-sm:block-Cursor",
  "i-ci-ve:ver25-Cursor",
  "r-cr-o:hor20-Cursor",
}, ",")
-- GitSignsStaged*: gitsigns fades the unstaged sign colors to mark a hunk as
-- staged, so the fade is the signal.
local DECORATIVE = {
  "Indent",
  "Whitespace",
  "NonText",
  "EndOfBuffer",
  "Border",
  "WinSeparator",
  "VertSplit",
  "GitSignsStaged",
}

local function channels(rgb)
  return math.floor(rgb / 0x10000) % 0x100, math.floor(rgb / 0x100) % 0x100, rgb % 0x100
end

local function linear(c8)
  local c = c8 / 255
  return c <= 0.03928 and c / 12.92 or ((c + 0.055) / 1.055) ^ 2.4
end

function M.luminance(rgb)
  local r, g, b = channels(rgb)
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
end

function M.contrast(a, b)
  local la, lb = M.luminance(a), M.luminance(b)
  local hi, lo = math.max(la, lb), math.min(la, lb)
  return (hi + 0.05) / (lo + 0.05)
end

local function mix(from, to, t)
  local fr, fg, fb = channels(from)
  local tr, tg, tb = channels(to)
  local function ch(a, b)
    return math.floor(a + (b - a) * t + 0.5)
  end
  return ch(fr, tr) * 0x10000 + ch(fg, tg) * 0x100 + ch(fb, tb)
end

local function min_contrast_against(color, backgrounds)
  local worst = math.huge
  for _, bg in ipairs(backgrounds) do
    worst = math.min(worst, M.contrast(color, bg))
  end
  return worst
end

--- Nudge `color` toward black or white (whichever reaches the ratio) until it
--- meets `target` against every background. Keeps hue as long as possible.
function M.ensure(color, backgrounds, target)
  if min_contrast_against(color, backgrounds) >= target then
    return color
  end
  local extreme = min_contrast_against(BLACK, backgrounds) >= min_contrast_against(WHITE, backgrounds) and BLACK
    or WHITE
  for t = LERP_STEP, 1, LERP_STEP do
    local candidate = mix(color, extreme, t)
    if min_contrast_against(candidate, backgrounds) >= target then
      return candidate
    end
  end
  return extreme
end

--- Groups the floor leaves alone: decoration meant to recede, and text
--- hidden on purpose by drawing it in its own background.
function M.exempt(name, fg, bg)
  if fg == bg then
    return true
  end
  for _, part in ipairs(DECORATIVE) do
    if name:find(part, 1, true) then
      return true
    end
  end
  return false
end

local function hl_color(group, attr)
  return vim.api.nvim_get_hl(0, { name = group, link = false })[attr]
end

local function normal_bg()
  return hl_color("Normal", "bg") or (vim.o.background == "light" and WHITE or BLACK)
end

local function raise_text()
  local fallback = normal_bg()
  for name, hl in pairs(vim.api.nvim_get_hl(0, {})) do
    local bg = hl.bg or fallback
    if hl.fg and not hl.link and not hl.reverse and not M.exempt(name, hl.fg, bg) then
      local fg = M.ensure(hl.fg, { bg }, MIN_CONTRAST)
      if fg ~= hl.fg then
        hl.fg = fg
        vim.api.nvim_set_hl(0, name, hl)
      end
    end
  end
end

local function cursor_backgrounds()
  local list = { normal_bg() }
  for _, group in ipairs({ "Visual", "CursorLine" }) do
    local bg = hl_color(group, "bg")
    if bg then
      list[#list + 1] = bg
    end
  end
  return list
end

local function raise_cursor()
  local bgs = cursor_backgrounds()
  local seed = hl_color("Cursor", "bg") or hl_color("Normal", "fg") or WHITE
  local cursor_bg = M.ensure(seed, bgs, MIN_CONTRAST)
  local cursor_fg = M.ensure(bgs[1], { cursor_bg }, MIN_CONTRAST)
  vim.api.nvim_set_hl(0, "Cursor", { fg = cursor_fg, bg = cursor_bg })
  vim.api.nvim_set_hl(0, "lCursor", { fg = cursor_fg, bg = cursor_bg })
end

function M.apply()
  raise_text()
  raise_cursor()
end

function M.setup()
  vim.o.guicursor = GUICURSOR
  vim.api.nvim_create_autocmd("ColorScheme", {
    group = vim.api.nvim_create_augroup("zach_contrast", { clear = true }),
    desc = "Enforce minimum text and cursor contrast",
    callback = M.apply,
  })
  M.apply()
end

return M
