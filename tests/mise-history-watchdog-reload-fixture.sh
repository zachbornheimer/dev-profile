#!/usr/bin/env bash
# Exercise launchd recovery without touching the login session or real watchers.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
watchdog="$root/bin/dev-profile-mise-history-watchdog"
fail() {
	echo "FAIL: $*" >&2
	exit 1
}
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export HOME="$work/home"
export MISE_HISTORY_LOG_DIR="$HOME/Library/Logs"
export CALLS="$work/calls" STATE="$work/state" SCENARIO=exconfig
mkdir -p "$work/bin" "$HOME/Library/LaunchAgents" "$MISE_HISTORY_LOG_DIR"
plist="$HOME/Library/LaunchAgents/dev.mise.mise-history.plist"
log="$MISE_HISTORY_LOG_DIR/mise-history-watchdog.log"
cat >"$work/bin/launchctl" <<'S'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >>"$CALLS"
state=$(cat "$STATE")
case "$1" in
list)
	[ "$state" != running ] || printf '12345\t0\tdev.mise.mise-history\n'
	;;
print)
	case "$state" in
	gone) exit 1 ;;
	removing) echo gone >"$STATE" ;;
	running) echo 'pid = 12345' ;;
	*) echo 'state = spawn scheduled'; echo "last exit code = ${EXIT_CODE:-78}: EX_CONFIG" ;;
	esac
	;;
kickstart) [ "$SCENARIO" != kickstart-ok ] || echo running >"$STATE" ;;
bootout)
	[ "$2" = "gui/$(id -u)/dev.mise.mise-history" ] || exit 2
	[ "$SCENARIO" = timeout ] || echo removing >"$STATE"
	;;
bootstrap)
	[ "$state" = gone ] || exit 3
	[ "$2" = "gui/$(id -u)" ] || exit 4
	[ "$3" = "$HOME/Library/LaunchAgents/dev.mise.mise-history.plist" ] || exit 5
	[ "$SCENARIO" != bootstrap-fail ] || exit 6
	echo running >"$STATE"
	;;
esac
S
cat >"$work/bin/mise" <<'S'
#!/usr/bin/env bash
if [ "$*" = 'dot status' ]; then
	printf 'watcher health (updated %ss ago)\n' "${HEALTH:-13}"
fi
S
printf '%s\n' '#!/usr/bin/env bash' 'exit 1' >"$work/bin/pgrep"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' >"$work/bin/sleep"
chmod +x "$work/bin/"*
export MISE_HISTORY_WATCHDOG_OS=Darwin MISE_HISTORY_WATCHDOG_PATH_PREFIX="$work/bin"
export MISE_HISTORY_WATCHDOG_MISE="$work/bin/mise"
export MISE_HISTORY_WATCHDOG_HEAL=/usr/bin/true MISE_HISTORY_WATCHDOG_REPAIR=/usr/bin/true
reset() {
	SCENARIO="$1"
	export EXIT_CODE=78 HEALTH=13
	echo stopped >"$STATE"
	: >"$CALLS"
	: >"$log"
	: >"$plist"
}
tick() { bash "$watchdog"; }
count() { awk -v cmd="$1" '$1 == cmd {n++} END {print n+0}' "$CALLS"; }
reloaded() {
	[ "$(cat "$STATE")" = running ] || fail "$SCENARIO: watcher not running"
	[ "$(count bootout)" = 1 ] || fail "$SCENARIO: expected one bootout"
	[ "$(count bootstrap)" = 1 ] || fail "$SCENARIO: expected one bootstrap"
	grep -q 'reloaded dev.mise.mise-history' "$log" || fail "$SCENARIO: reload not logged"
}
reset exconfig
tick
reloaded
grep -q 'last exit code = 78' "$log" || fail 'EX_CONFIG observation not logged'
[ "$(wc -l <"$log" | tr -d ' ')" = 1 ] || fail 'reload produced multiple log lines'
reset kickstart-stuck
export EXIT_CODE=1
tick
reloaded
[ "$(count kickstart)" = 1 ] || fail 'missing restart attempt'
grep -q 'no pid after kickstart' "$log" || fail 'failed restart not logged'
reset kickstart-ok
export EXIT_CODE=1
tick
[ "$(cat "$STATE")" = running ] || fail 'kickstart did not restore service'
[ "$(count bootout)" = 0 ] || fail 'successful kickstart triggered reload'
reset healthy
echo running >"$STATE"
tick
[ "$(count bootout)" = 0 ] || fail 'owned watcher was reloaded'
[ "$(count kickstart)" = 0 ] || fail 'healthy watcher was restarted'
[ ! -s "$log" ] || fail 'healthy watcher generated noise'
reset missing
rm "$plist"
tick
[ "$(count bootout)" = 0 ] || fail 'missing plist caused bootout'
grep -q 'plist missing' "$log" || fail 'missing plist not logged'
reset timeout
export HEALTH=900
tick
[ "$(count bootout)" = 1 ] || fail 'reload attempted more than once per tick'
[ "$(count bootstrap)" = 0 ] || fail 'bootstrap ran before service disappeared'
# One diagnostic print precedes the fifteen bounded bootout probes.
[ "$(count print)" = 16 ] || fail 'bootout wait was unbounded'
grep -q 'timed out' "$log" || fail 'bootout timeout not logged'
reset bootstrap-fail
tick
[ "$(count bootstrap)" = 1 ] || fail 'bootstrap was not attempted'
grep -q 'bootstrap failed' "$log" || fail 'bootstrap failure not logged'
echo 'mise history watchdog reload: ok'
