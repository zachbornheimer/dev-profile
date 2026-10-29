# Fast mouse clicker using uv and pyautogui
# Usage: click [count|Inf] [--delay-ms <ms>] [--kill-key <key>]
click() {
	local delay_ms=100
	local clicks=100
	local kill_key=""

	while [[ $# -gt 0 ]]; do
		case "$1" in
		-delay-ms | --delay-ms)
			if [[ $# -lt 2 ]]; then
				__ -t failed "click: --delay-ms requires a value"
				return 2
			fi
			delay_ms="$2"
			shift 2
			;;
		--delay-ms=*)
			delay_ms="${1#*=}"
			shift
			;;
		-kill-key | --kill-key)
			if [[ $# -lt 2 ]]; then
				__ -t failed "click: --kill-key requires a key (for example f4)"
				return 2
			fi
			kill_key="$2"
			shift 2
			;;
		--kill-key=*)
			kill_key="${1#*=}"
			shift
			;;
		[0-9]*)
			if [[ "$1" =~ ^[0-9]+$ ]]; then
				clicks="$1"
			else
				__ -t failed "click: invalid click count '$1'"
				return 2
			fi
			shift
			;;
		Inf | inf)
			clicks="Inf"
			shift
			;;
		*)
			__ -t failed "click: unknown argument '$1'"
			return 2
			;;
		esac
	done

	if [[ "$clicks" == "Inf" && -z "$kill_key" ]]; then
		__ -t failed "click: Inf requires --kill-key (for example --kill-key f4)"
		return 2
	fi

	if [[ ! "$delay_ms" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
		__ -t failed "click: delay must be a non-negative number of milliseconds"
		return 2
	fi

	local delay_sec
	delay_sec=$(awk "BEGIN {print $delay_ms / 1000}")
	__ "Starting in 3 seconds... Clicking $clicks times with a ${delay_ms}ms delay${kill_key:+; press $kill_key to stop}."
	sleep 3

	local uv_args=(--with pyautogui)
	if [[ -n "$kill_key" ]]; then
		uv_args+=(--with keyboard)
	fi
	uv run "${uv_args[@]}" python - "$clicks" "$delay_sec" "$kill_key" <<'PY'
import sys
import time
import pyautogui

clicks, delay, kill_key = sys.argv[1:]
delay = float(delay)
pyautogui.PAUSE = 0

if kill_key:
    import keyboard
    keyboard.hook(lambda event: (_ for _ in ()).throw(KeyboardInterrupt()) if event.name.lower() == kill_key.lower() else None)

try:
    count = 0
    while clicks == "Inf" or count < int(clicks):
        pyautogui.click()
        count += 1
        if delay:
            time.sleep(delay)
except KeyboardInterrupt:
    print(f"Stopped after {count} click(s).")
PY
}

click-1pwd() {
	local hours=14
	# parse --hours <n>
	while [[ $# -gt 0 ]]; do
		case "$1" in
		--hours)
			hours="$2"
			shift 2
			;;
		--hours=*)
			hours="${1#*=}"
			shift
			;;
		*)
			__ -t failed "click-1pwd: unknown arg '$1'"
			return 2
			;;
		esac
	done

	if ! command -v cliclick >/dev/null 2>&1; then
		__ -t failed "click-1pwd: cliclick not found (brew install cliclick)"
		return 1
	fi

	local end=$(($(date +%s) + hours * 3600))
	__ "click-1pwd: clicking 1101,596 every 30s for ${hours}h (until $(date -r "$end" '+%H:%M:%S'))"
	while [[ $(date +%s) -lt $end ]]; do
		cliclick c:1101,596
		sleep 30
	done
}
