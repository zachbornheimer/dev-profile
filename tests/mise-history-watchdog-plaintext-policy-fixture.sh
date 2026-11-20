#!/usr/bin/env bash
# Step 5: `history.allow_plaintext_history` must be false on every machine, and a
# machine whose working copy still holds `true` republishes it, so the watchdog
# writes the setting back and saves it. Stubs stand in for mise; no real config
# changes and no live service is touched.
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
export CALLS="$work/calls" POLICY=true SET_FAILS=0
mkdir -p "$work/bin" "$MISE_HISTORY_LOG_DIR"
log="$MISE_HISTORY_LOG_DIR/mise-history-watchdog.log"

# The watcher looks healthy, so only the policy step can produce output.
cat >"$work/bin/launchctl" <<'S'
#!/usr/bin/env bash
[ "$1" = list ] && printf '12345\t0\tdev.mise.mise-history\n'
exit 0
S
cat >"$work/bin/mise" <<'S'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >>"$CALLS"
case "$*" in
"settings get history.allow_plaintext_history") printf '%s\n' "$POLICY" ;;
"settings set history.allow_plaintext_history false")
	[ "$SET_FAILS" = 0 ] || exit 1
	;;
esac
exit 0
S
cat >"$work/bin/repair" <<'S'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$REPAIRS"
exit 0
S
printf '%s\n' '#!/usr/bin/env bash' 'exit 1' >"$work/bin/pgrep"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' >"$work/bin/sleep"
chmod +x "$work/bin"/*
export REPAIRS="$work/repairs"
: >"$REPAIRS"
export MISE_HISTORY_WATCHDOG_OS=Darwin MISE_HISTORY_WATCHDOG_PATH_PREFIX="$work/bin"
export MISE_HISTORY_WATCHDOG_MISE="$work/bin/mise"
export MISE_HISTORY_WATCHDOG_HEAL=/usr/bin/true MISE_HISTORY_WATCHDOG_REPAIR="$work/bin/repair"

reset() {
	: >"$CALLS"
	: >"$log"
	: >"$REPAIRS"
}
tick() { bash "$watchdog" >/dev/null 2>&1 || true; }
called() { grep -qxF "$1" "$CALLS" 2>/dev/null; }

# (a) true: the setting is written back and saved, and the heal is logged.
reset
POLICY=true SET_FAILS=0
tick
called 'settings set history.allow_plaintext_history false' || fail "(a) true was not set false"
called 'dot save' || fail "(a) the fix was not saved"
grep -q 'restored history.allow_plaintext_history = false' "$log" || fail "(a) heal not logged"

# (b) false: nothing is written or saved, and the tick is silent.
reset
POLICY=false
tick
called 'settings set history.allow_plaintext_history false' && fail "(b) false was rewritten"
called 'dot save' && fail "(b) a clean policy still saved"
[ ! -s "$log" ] || fail "(b) a clean policy generated noise"

# (c) a build that cannot answer `settings get` is silence, not a policy break.
reset
POLICY=""
tick
called 'settings set history.allow_plaintext_history false' && fail "(c) unreadable policy was rewritten"
[ ! -s "$log" ] || fail "(c) unreadable policy generated noise"

# (d) a policy that cannot be written back is a worker's job, and the class it
# escalates to must be one the repair tool accepts: an unknown class is dropped
# with a message, so the failure would be reported to nobody.
reset
POLICY=true SET_FAILS=1
tick
grep -q -- '--class publishing-blocked' "$REPAIRS" || fail "(d) unwritable policy was not escalated"
class="$(sed -n 's/^--class \([^ ]*\).*/\1/p' "$REPAIRS" | head -1)"
[ -n "$class" ] || fail "(d) the escalation carried no class"
if bash "$root/bin/dev-profile-mise-history-repair" --class "$class" --detail fixture --dry-run 2>&1 |
	grep -q 'unknown class'; then
	fail "(d) the repair tool does not accept the class it was given: $class"
fi
grep -q 'publishing-blocked' "$log" || fail "(d) the escalation verdict was not logged"

echo 'mise history watchdog plaintext policy: ok'
