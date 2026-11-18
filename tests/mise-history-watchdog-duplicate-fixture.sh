#!/usr/bin/env bash
# Step 1 of the watchdog must keep the service's whole process tree (the LaunchAgent's
# sh wrapper and its mise child) and kill only watchers outside it. Stubs and
# throwaway sleep processes stand in for everything; no live service is touched.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
watchdog="$root/bin/dev-profile-mise-history-watchdog"
fail() {
	echo "FAIL: $*" >&2
	exit 1
}
work="$(mktemp -d)"
pids=()
cleanup() {
	for p in ${pids[@]+"${pids[@]}"}; do kill "$p" 2>/dev/null || true; done
	rm -rf "$work"
}
trap cleanup EXIT
export HOME="$work/home"
unset MISE_HISTORY_LOG_DIR
mkdir -p "$HOME/Library/Logs" "$work/bin"
export MISE_HISTORY_LOG_DIR="$HOME/Library/Logs"

# Stubs read $TABLE ("pid ppid" lines), $WATCHERS (pgrep output), $SERVICE_PID.
cat >"$work/bin/launchctl" <<'S'
#!/usr/bin/env bash
[ "$1" = list ] && printf '%s\t0\tdev.mise.mise-history\n' "$SERVICE_PID"
exit 0
S
cat >"$work/bin/systemctl" <<'S'
#!/usr/bin/env bash
case "$*" in *"show -p MainPID"*) echo "$SERVICE_PID" ;; esac
exit 0
S
cat >"$work/bin/pgrep" <<'S'
#!/usr/bin/env bash
cat "$WATCHERS"
S
cat >"$work/bin/ps" <<'S'
#!/usr/bin/env bash
# ps -o ppid= -p PID
awk -v p="$4" '$1 == p {print $2}' "$TABLE"
S
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' >"$work/bin/mise"
chmod +x "$work/bin"/*
export TABLE="$work/table" WATCHERS="$work/watchers"

# Sets SPAWNED; runs in this shell so no command substitution waits on the child's pipe.
spawn() {
	sleep 60 >/dev/null 2>&1 &
	SPAWNED=$!
	pids+=("$SPAWNED")
}
alive() { kill -0 "$1" 2>/dev/null; }
run() { # os
	MISE_HISTORY_WATCHDOG_OS="$1" MISE_HISTORY_WATCHDOG_PATH_PREFIX="$work/bin" \
		MISE_HISTORY_WATCHDOG_MISE="$work/bin/mise" MISE_HISTORY_WATCHDOG_HEAL=/usr/bin/true \
		MISE_HISTORY_WATCHDOG_REPAIR=/usr/bin/true bash "$watchdog" >/dev/null 2>&1 || true
}

# (a) wrapper sh + mise child: nothing killed
spawn
sh_pid=$SPAWNED
spawn
child=$SPAWNED
printf '%s 1\n%s %s\n' "$sh_pid" "$child" "$sh_pid" >"$TABLE"
printf '%s\n%s\n' "$sh_pid" "$child" >"$WATCHERS"
SERVICE_PID=$sh_pid run Darwin
sleep 0.3
alive "$sh_pid" || fail "(a) wrapper sh killed"
alive "$child" || fail "(a) service's mise child killed"

# (b) plus an unrelated watcher: only it is killed
spawn
stray=$SPAWNED
printf '%s 1\n%s %s\n%s 1\n' "$sh_pid" "$child" "$sh_pid" "$stray" >"$TABLE"
printf '%s\n%s\n%s\n' "$sh_pid" "$child" "$stray" >"$WATCHERS"
SERVICE_PID=$sh_pid run Darwin
sleep 0.3
alive "$sh_pid" || fail "(b) wrapper sh killed"
alive "$child" || fail "(b) service's mise child killed"
if alive "$stray"; then fail "(b) unrelated watcher survived"; fi

# (c) Linux: MainPID is the mise process itself
spawn
main=$SPAWNED
printf '%s 1\n' "$main" >"$TABLE"
printf '%s\n' "$main" >"$WATCHERS"
SERVICE_PID=$main run Linux
sleep 0.3
alive "$main" || fail "(c) Linux MainPID killed"
echo "OK"
