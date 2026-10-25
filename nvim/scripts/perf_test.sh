#!/usr/bin/env bash
# Headless proof for always-on nvim session timings + zsh wall wrapper.
# Drives the real worktree nvim config (not a reimplementation).
set -euo pipefail

# scripts/ → nvim/ → dot_config/ → home/ → repo root
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
NVIM_SRC="$ROOT/home/dot_config/nvim"
ZSH_WRAP="$ROOT/home/dot_config/zsh/nvim-perf.zsh"
[[ -f "$NVIM_SRC/init.lua" ]] || {
	echo "FAIL: cannot find nvim config at $NVIM_SRC" >&2
	exit 1
}

SCRATCH="${PERF_TEST_SCRATCH:-${TMPDIR:-/tmp}/nvim-perf-test-$$}"
mkdir -p "$SCRATCH"
LOG_DIR="$SCRATCH/log"
CONFIG_HOME="$SCRATCH/xdg-config"
STATE_HOME="$SCRATCH/xdg-state"
mkdir -p "$LOG_DIR" "$CONFIG_HOME" "$STATE_HOME"
ln -sfn "$NVIM_SRC" "$CONFIG_HOME/nvim"

export XDG_CONFIG_HOME="$CONFIG_HOME"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_STATE_HOME="$STATE_HOME"

fail() {
	echo "FAIL: $*" >&2
	exit 1
}

pass() {
	echo "PASS: $*"
}

jsonl_has_event() {
	local file="$1" event="$2"
	grep -q "\"event\":\"${event}\"" "$file"
}

# --- A/B: session events via isolated headless nvim ---
SESSION_LOG="$LOG_DIR/session.jsonl"
rm -f "$SESSION_LOG"
export NVIM_PERF_LOG="$SESSION_LOG"
unset NVIM_PROF || true

# +qa: session_start + leave events (VimEnter skipped when +qa is a startup cmd)
timeout 90 nvim --headless +qa 2>"$SCRATCH/session.err" || fail "nvim +qa exited $?"
jsonl_has_event "$SESSION_LOG" "session_start" || fail "missing session_start in $SESSION_LOG"
jsonl_has_event "$SESSION_LOG" "vim_leave_pre" || fail "missing vim_leave_pre"
jsonl_has_event "$SESSION_LOG" "vim_leave" || fail "missing vim_leave"
pass "session_start + vim_leave_pre + vim_leave (+qa)"

# Deferred quit so VimEnter fires (acceptance: vim_enter present)
ENTER_LOG="$LOG_DIR/enter.jsonl"
rm -f "$ENTER_LOG"
export NVIM_PERF_LOG="$ENTER_LOG"
timeout 90 nvim --headless \
	-c 'lua vim.defer_fn(function() vim.cmd("qa") end, 50)' \
	2>"$SCRATCH/enter.err" || fail "deferred qa exited $?"
jsonl_has_event "$ENTER_LOG" "vim_enter" || fail "missing vim_enter"
jsonl_has_event "$ENTER_LOG" "session_start" || fail "missing session_start on enter run"
pass "vim_enter (deferred qa)"

# --- C: slow autocmd >= 50ms, with src from wrap-time debug.getinfo ---
SLOW_LOG="$LOG_DIR/slow.jsonl"
rm -f "$SLOW_LOG"
export NVIM_PERF_LOG="$SLOW_LOG"
export NVIM_PERF_THRESHOLD_MS=50
timeout 90 nvim --headless \
	-c 'lua vim.api.nvim_create_autocmd("User", { pattern = "PerfSlow", desc = "slow test", callback = function() vim.wait(60) end })' \
	-c 'doautocmd User PerfSlow' \
	-c 'qa' \
	2>"$SCRATCH/slow.err" || fail "slow autocmd run exited $?"
grep -q '"event":"autocmd"' "$SLOW_LOG" || fail "missing autocmd event"
# ms field >= 50 (integer or float); BSD awk has no match() 3-arg form
slow_ok=0
slow_src_ok=0
while IFS= read -r line; do
	case "$line" in
	*'"event":"autocmd"'*)
		ms="${line#*\"ms\":}"
		ms="${ms%%,*}"
		ms="${ms%%\}*}"
		if awk -v n="$ms" 'BEGIN { exit !(n+0 >= 50) }'; then
			slow_ok=1
			case "$line" in
			*'"src":'*) slow_src_ok=1 ;;
			esac
			break
		fi
		;;
	esac
done <"$SLOW_LOG"
[[ "$slow_ok" -eq 1 ]] || fail "autocmd ms < 50 in $SLOW_LOG"
[[ "$slow_src_ok" -eq 1 ]] || fail "slow autocmd row missing src (debug.getinfo) in $SLOW_LOG"
pass "slow autocmd ms >= 50 with src"
unset NVIM_PERF_THRESHOLD_MS

# --- D: NVIM_PROF profile dump ---
export NVIM_PROF=1
export NVIM_PERF_LOG="$LOG_DIR/prof-session.jsonl"
rm -f "$LOG_DIR/prof-session.jsonl"
timeout 90 nvim --headless +qa 2>"$SCRATCH/prof.err" || fail "NVIM_PROF run exited $?"
PROFILE="$(find "$STATE_HOME" -name 'profile-*.log' -type f 2>/dev/null | head -1)"
[[ -n "$PROFILE" ]] || fail "no profile-*.log under $STATE_HOME"
[[ -s "$PROFILE" ]] || fail "profile log empty: $PROFILE"
pass "NVIM_PROF wrote non-empty $(basename "$PROFILE")"
unset NVIM_PROF

# --- E: zsh wall wrapper ---
[[ -f "$ZSH_WRAP" ]] || fail "missing wrapper $ZSH_WRAP"
WALL_LOG="$LOG_DIR/wall.jsonl"
rm -f "$WALL_LOG"
export NVIM_PERF_LOG="$WALL_LOG"
# Use a bare nvim for wall timing (wrapper under test); config isolation optional here
zsh -f -c "
  source '$ZSH_WRAP'
  nvim --headless +qa
  exit \$?
" 2>"$SCRATCH/wall.err" || fail "zsh wrapper nvim exited $?"
grep -q '"event":"wall"' "$WALL_LOG" || fail "missing wall event"
grep -Eq '"ms":[0-9]+(\.[0-9]+)?' "$WALL_LOG" || fail "wall ms not numeric"
grep -q '"rc":0' "$WALL_LOG" || fail "wall rc not 0"
pass "zsh wall event ms+rc 0"

# Preserve exit code
rm -f "$WALL_LOG"
set +e
zsh -f -c "
  source '$ZSH_WRAP'
  nvim --headless -c 'cq 7'
  exit \$?
" 2>"$SCRATCH/wall7.err"
wall_rc=$?
set -e
[[ "$wall_rc" -eq 7 ]] || fail "wrapper swallowed exit (got $wall_rc, want 7)"
grep -q '"rc":7' "$WALL_LOG" || fail "wall line missing rc 7"
pass "zsh wrapper preserves rc 7"

# --- F: forbidden plugin name must not appear in config ---
# Pattern built at runtime so this file itself is not a false positive for `rg`.
forbid="snacks"'.'"nvim"
if command -v rg >/dev/null 2>&1; then
	if rg -q -F "$forbid" "$NVIM_SRC"; then
		fail "$forbid referenced under nvim config"
	fi
else
	if grep -R -F -q "$forbid" "$NVIM_SRC"; then
		fail "$forbid referenced under nvim config"
	fi
fi
pass "no $forbid"

# --- :NvimPerf registered ---
grep -q 'NvimPerf' "$NVIM_SRC/lua/zach/core/perf.lua" || fail ":NvimPerf not in perf.lua"
pass ":NvimPerf command present in perf.lua"

# --- G: Gitsigns VimLeavePre detach is skipped ---
MARKER="$LOG_DIR/gitsigns-detached"
rm -f "$MARKER"
export NVIM_PERF_LOG="$LOG_DIR/gitsigns.jsonl"
timeout 90 nvim --headless \
	-c "lua vim.api.nvim_create_autocmd('VimLeavePre', { desc = 'Gitsigns: detach from all buffers', callback = function() vim.fn.writefile({'detached'}, [[$MARKER]]) end })" \
	-c 'qa' \
	2>"$SCRATCH/gitsigns.err" || fail "gitsigns-skip run exited $?"
[[ ! -f "$MARKER" ]] || fail "Gitsigns detach still ran (wrote $MARKER)"
pass "Gitsigns detach skipped on quit"

# --- H: fs_event on cwd must not stall quit (Dropbox hang was ~15s) ---
export NVIM_PERF_LOG="$LOG_DIR/fsevent.jsonl"
FS_START=$(date +%s)
timeout 20 nvim --headless \
	-c 'lua local h=assert(vim.uv.new_fs_event()); h:start(vim.fn.getcwd(), {}, function() end)' \
	-c 'qa' \
	2>"$SCRATCH/fsevent.err" || fail "fs_event quit exited $?"
FS_SECS=$(($(date +%s) - FS_START))
[[ "$FS_SECS" -lt 5 ]] || fail "fs_event stall on quit (${FS_SECS}s)"
pass "fs_event quit in ${FS_SECS}s"

# --- I: auto_reload_on_write must be false (watchers off ⇒ default true reloads on :w) ---
TREE_LUA="$NVIM_SRC/lua/zach/plugins/nvim-tree.lua"
grep -q 'auto_reload_on_write = false' "$TREE_LUA" ||
	fail "auto_reload_on_write = false missing from nvim-tree.lua"
grep -q 'filesystem_watchers' "$TREE_LUA" || fail "filesystem_watchers block missing"
pass "auto_reload_on_write = false (watchers stay off)"

# --- J: :w with nvim-tree explorer loaded against ≥40-subdir tree < 500ms ---
# Avoid tree.open (headless UI hang): load plugin, core.init explorer, measure write().
FAT="$SCRATCH/fat-tree"
rm -rf "$FAT"
mkdir -p "$FAT"
for ((i = 1; i <= 40; i++)); do
	mkdir -p "$FAT/subdir_$i"
done
printf 'hello\n' >"$FAT/scratch.txt"
WRITE_LOG="$LOG_DIR/write-tree.jsonl"
WRITE_MS_FILE="$SCRATCH/write-ms.txt"
rm -f "$WRITE_LOG" "$WRITE_MS_FILE"
export NVIM_PERF_LOG="$WRITE_LOG"
# No file on argv: VimEnter auto-open returns early (no hang on tree.open).
timeout 20 nvim --headless \
	-c "lua vim.defer_fn(function()
    local fat = [[$FAT]]
    local out = [[$WRITE_MS_FILE]]
    local ok, err = pcall(function()
      vim.cmd.cd(fat)
      vim.cmd.edit('scratch.txt')
      require('lazy').load({ plugins = { 'nvim-tree.lua' } })
      require('nvim-tree.core').init(vim.fn.getcwd())
      vim.bo.modified = true
      local t0 = vim.uv.hrtime()
      vim.cmd.write()
      local ms = (vim.uv.hrtime() - t0) / 1e6
      vim.fn.writefile({ string.format('%.3f', ms) }, out)
    end)
    if not ok then
      vim.fn.writefile({ 'ERR:' .. tostring(err) }, out)
    end
    vim.cmd('qa!')
  end, 100)" \
	2>"$SCRATCH/write-tree.err" || fail "write-with-tree exited $? (see $SCRATCH/write-tree.err)"
[[ -f "$WRITE_MS_FILE" ]] || fail "write-with-tree produced no $WRITE_MS_FILE"
WRITE_MS="$(cat "$WRITE_MS_FILE")"
case "$WRITE_MS" in
ERR:*) fail "write-with-tree lua error: $WRITE_MS" ;;
esac
awk -v n="$WRITE_MS" 'BEGIN { exit !(n+0 < 500) }' ||
	fail "write with nvim-tree took ${WRITE_MS}ms (>= 500)"
# Any BufWritePost autocmd rows in the perf log must be under 500ms
while IFS= read -r line; do
	case "$line" in
	*'"event":"autocmd"'*)
		case "$line" in
		*BufWritePost*)
			ms="${line#*\"ms\":}"
			ms="${ms%%,*}"
			ms="${ms%%\}*}"
			if awk -v n="$ms" 'BEGIN { exit !(n+0 >= 500) }'; then
				fail "BufWritePost autocmd ms >= 500 ($ms) in $WRITE_LOG"
			fi
			;;
		esac
		;;
	esac
done <"$WRITE_LOG"
pass "write with nvim-tree ${WRITE_MS}ms (< 500)"

# --- K: vim_leave_pre carries session_ms (ms is callback duration, not session age) ---
grep -q '"event":"vim_leave_pre"' "$SESSION_LOG" || fail "session log missing vim_leave_pre for session_ms check"
leave_pre_line="$(grep '"event":"vim_leave_pre"' "$SESSION_LOG" | head -1)"
case "$leave_pre_line" in
*'"session_ms":'*) ;;
*) fail "vim_leave_pre missing session_ms: $leave_pre_line" ;;
esac
pass "vim_leave_pre has session_ms"

# --- L: quit steps emit named spans on +qa ---
SPAN_LOG="$LOG_DIR/quit-spans.jsonl"
rm -f "$SPAN_LOG"
export NVIM_PERF_LOG="$SPAN_LOG"
timeout 90 nvim --headless +qa 2>"$SCRATCH/quit-spans.err" || fail "quit-spans +qa exited $?"
span_quit_ok=0
while IFS= read -r line; do
	case "$line" in
	*'"event":"span"'*)
		case "$line" in
		*'"name":"quit.unref_fs"'* | *'"name":"quit.skip_gitsigns"'*)
			span_quit_ok=1
			break
			;;
		esac
		;;
	esac
done <"$SPAN_LOG"
[[ "$span_quit_ok" -eq 1 ]] || fail "no quit.unref_fs / quit.skip_gitsigns span in $SPAN_LOG"
pass "quit named span on +qa"

# --- M: perf.span always logs duration (no 50ms gate); vim.wait(60) → ms>=50 ---
SPAN_DUR_LOG="$LOG_DIR/span-dur.jsonl"
rm -f "$SPAN_DUR_LOG"
export NVIM_PERF_LOG="$SPAN_DUR_LOG"
timeout 90 nvim --headless \
	-c 'lua require("zach.core.perf").span("test.wait60", function() vim.wait(60) end)' \
	-c 'qa' \
	2>"$SCRATCH/span-dur.err" || fail "span duration run exited $?"
span_dur_ok=0
while IFS= read -r line; do
	case "$line" in
	*'"event":"span"'*)
		case "$line" in
		*'"name":"test.wait60"'*)
			ms="${line#*\"ms\":}"
			ms="${ms%%,*}"
			ms="${ms%%\}*}"
			if awk -v n="$ms" 'BEGIN { exit !(n+0 >= 50) }'; then
				span_dur_ok=1
				break
			fi
			;;
		esac
		;;
	esac
done <"$SPAN_DUR_LOG"
[[ "$span_dur_ok" -eq 1 ]] || fail "span test.wait60 ms < 50 or missing in $SPAN_DUR_LOG"
pass "span helper ms >= 50 (vim.wait 60)"

# --- N: appearance preferred_background uses a cache (not system on every call) ---
APP_LUA="$NVIM_SRC/lua/zach/core/appearance.lua"
grep -Eq 'cache|cached|CACHE|ttl|TTL|last_read|last_check' "$APP_LUA" ||
	fail "appearance.lua missing cache for preferred_background"
# Prove cache: after one warm call, a second call must not invoke vim.fn.system.
# (options.lua may already have warmed the cache at load — that is fine.)
APP_MS_FILE="$SCRATCH/appearance-ms.txt"
rm -f "$APP_MS_FILE"
export NVIM_PERF_LOG="$LOG_DIR/appearance.jsonl"
timeout 90 nvim --headless \
	-c "lua local a=require('zach.core.appearance')
    a.preferred_background()
    local calls = 0
    local orig = vim.fn.system
    vim.fn.system = function(...)
      calls = calls + 1
      return orig(...)
    end
    local t0 = vim.uv.hrtime()
    a.preferred_background()
    local second = (vim.uv.hrtime() - t0) / 1e6
    vim.fn.system = orig
    vim.fn.writefile({ string.format('%d %.3f', calls, second) }, [[$APP_MS_FILE]])
  " \
	-c 'qa' \
	2>"$SCRATCH/appearance.err" || fail "appearance cache run exited $?"
[[ -f "$APP_MS_FILE" ]] || fail "appearance cache produced no timings"
read -r APP_CALLS APP_SECOND <"$APP_MS_FILE"
[[ "$APP_CALLS" -eq 0 ]] || fail "preferred_background invoked system ${APP_CALLS}x on cache hit"
awk -v s="$APP_SECOND" 'BEGIN { exit !(s+0 < 5) }' ||
	fail "preferred_background cache hit too slow (${APP_SECOND}ms)"
pass "appearance cache hit: 0 system calls, ${APP_SECOND}ms"

echo "ALL CHECKS PASSED"
echo "artifacts under $SCRATCH"
