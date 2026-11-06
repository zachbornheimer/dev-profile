#!/usr/bin/env bash
# The watchdog must hand a failure it cannot heal to one atask objective and one
# worker run on it, and must reach a person only when no worker could be started
# or every attempt has failed.
#
# Everything the watchdog shells out to is a stub, and the atask engine runs
# against a throwaway database, so the fixture drives every branch without
# touching the live history service, the live board, or the user's notifications.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
watchdog="$root/bin/dev-profile-mise-history-watchdog"
repair="$root/bin/dev-profile-mise-history-repair"

fail() {
	echo "FAIL: $*" >&2
	exit 1
}

# atask is a mise shim here, and mise finds its tools under the real HOME, so
# the fixture calls it through a wrapper that restores HOME for that one call.
# Both lookups are checked: a tool missing from PATH used to end the fixture
# silently, and doctor could only report that the fixture failed.
real_home="$HOME"
atask_bin="$(command -v atask)" || fail 'atask is not on PATH; the profile pins it, so run mise install'
python3_bin="$(command -v python3)" || fail 'python3 is not on PATH'
python_dir="$(dirname "$python3_bin")"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

export HOME="$work/home"
mkdir -p "$HOME/Library/Logs" "$work/bin" "$HOME/.local/bin"
printf '%s\n' '#!/usr/bin/env bash' "export HOME=\"$real_home\"" "exec \"$atask_bin\" \"\$@\"" >"$work/bin/atask"
chmod +x "$work/bin/atask"
atask="$work/bin/atask"
# The stub directory first, then the real python3 and the system tools; launchctl
# and pgrep are stubbed so no tick can touch a real process on this machine.
export PATH="$work/bin:$python_dir:/usr/bin:/bin"
export ATASK_DB="$work/atask.db"
export ATASK_OUTPUT=json

# --- stubs ------------------------------------------------------------------
printf '%s\n' '#!/usr/bin/env bash' 'case "$*" in' '"dot status") cat "$MISE_STATUS" ;;' 'esac' 'exit 0' >"$work/bin/mise"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\\n" "$*" >>"$NOTIFY_CALLS"' >"$work/bin/notify"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' >"$work/bin/launchctl"
printf '%s\n' '#!/usr/bin/env bash' 'exit 1' >"$work/bin/pgrep"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' >"$work/bin/heal-ok"
printf '%s\n' '#!/usr/bin/env bash' 'echo "heal: multi-line entry needs a hand edit: ~/.config/x.toml" >&2' 'exit 1' >"$work/bin/heal-fail"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\\n" "$*" >>"$SPAWN_CALLS"' 'exec sleep 30' >"$work/bin/capability-ok"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\\n" "$*" >>"$SPAWN_CALLS"' 'echo "capability: no such tool start_atask_task"' 'exit 3' >"$work/bin/capability-fail"
cat >"$work/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$SYSTEMCTL_CALLS"
case "$*" in
*"show -p MainPID"*) echo "${FAKE_MAINPID:-0}" ;;
esac
exit 0
EOF
cat >"$work/bin/systemd-run" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$SYSTEMD_RUN_CALLS"
[ -z "${FAKE_SYSTEMD_RUN_FAIL:-}" ] || exit 1
exit 0
EOF
chmod +x "$work/bin/"*
# The watchdog rebuilds PATH from $HOME, so a stub only counts if it sits where
# that PATH looks; the fixture's own PATH is not enough. Without this a Linux
# runner finds no launchctl at all and the tick exits non-zero under pipefail.
ln -sf "$work/bin/launchctl" "$work/bin/pgrep" "$HOME/.local/bin/"

cd "$work"
"$atask" project add probe >/dev/null

unset MISE_HISTORY_REPAIR_STATE MISE_HISTORY_REPAIR_MAX_ATTEMPTS MISE_HISTORY_REPAIR_COOLDOWN_S
export MISE_HISTORY_WATCHDOG_MISE="$work/bin/mise"
export MISE_HISTORY_WATCHDOG_HEAL="$work/bin/heal-ok"
export MISE_HISTORY_WATCHDOG_REPAIR="$repair"
export MISE_HISTORY_WATCHDOG_NOTIFY="$work/bin/notify"
export MISE_HISTORY_REPAIR_SPAWN="$work/bin/capability-ok"
export MISE_HISTORY_REPAIR_ATASK="$atask"
export MISE_HISTORY_REPAIR_PROJECT=probe
export MISE_HISTORY_REPAIR_STATE="$work/state"
export SPAWN_CALLS="$work/spawn-calls"
export NOTIFY_CALLS="$work/notify-calls"
export MISE_STATUS="$work/status"
export SYSTEMCTL_CALLS="$work/systemctl-calls"
export SYSTEMD_RUN_CALLS="$work/systemd-run-calls"
# The sections below run as a Mac; the Linux section switches the OS itself.
export MISE_HISTORY_WATCHDOG_OS=Darwin
# The watchdog resets PATH to the machine's own; this keeps the stubs in front of it.
export MISE_HISTORY_WATCHDOG_PATH_PREFIX="$work/bin"
export MISE_HISTORY_REPAIR_STARTUP_GRACE_S=1
log="$HOME/Library/Logs/mise-history-watchdog.log"
spawn_log="$HOME/Library/Logs/mise-history-repair.log"

reset() {
	rm -rf "$work/state"
	mkdir -p "$work/state"
	: >"$SPAWN_CALLS"
	: >"$NOTIFY_CALLS"
	: >"$log"
	: >"$spawn_log"
}

stalled() {
	printf '%s\n' '✓ 100 entries up to date (`--verbose` lists them all)' 'Repository' '  ✗ last error: ~/.omp/agent/extensions/x is not a directory; resolve its type before pulling (failing since 2026-11-04 10:42, 12 attempt(s))' >"$MISE_STATUS"
}

healthy() {
	printf '%s\n' '✓ 100 entries up to date (`--verbose` lists them all)' '  ✓ 908 checkpoints · latest 1147 (baseline, 2026-11-04 16:54)' '  watcher health (updated 13s ago): last capture 2026-11-04 18:00' >"$MISE_STATUS"
}

tick() {
	# Keep the watchdog's own words: a silent non-zero exit is what made the
	# CI runner's failure take a day to place.
	if ! out="$(bash "$watchdog" 2>&1)"; then
		printf '%s\n' "--- watchdog output ($1) ---" "$out" >&2
		fail "the watchdog exited non-zero on a $1 tick"
	fi
}

spawns() { wc -l <"$SPAWN_CALLS" | tr -d ' '; }
notifications() { wc -l <"$NOTIFY_CALLS" | tr -d ' '; }
filed_id() { sed -n 's/.*--input {"id":"\(at-[a-z0-9]*\)".*/\1/p' "$SPAWN_CALLS" | head -1; }

# --- a stalled publish files one objective and spawns one run ----------------
reset
stalled
tick 'first escalation'
[ "$(spawns)" = 1 ] || fail "a blocked publish did not spawn exactly one run: $(cat "$SPAWN_CALLS")"
[ "$(notifications)" = 0 ] || fail "the user was notified before any worker could try: $(cat "$NOTIFY_CALLS")"
grep -q 'run start_atask_task --input {"id":"at-[a-z0-9]*","onComplete":"merge","timeout_s":5400}' "$SPAWN_CALLS" || fail "the run was not spawned through start_atask_task: $(cat "$SPAWN_CALLS")"
grep -q "publishing-blocked: spawned at-" "$log" || fail "the spawn was not logged: $(cat "$log")"
task="$(filed_id)"
[ -n "$task" ] || fail 'no objective id in the spawn call'
objective="$("$atask" show "$task" --json)"
grep -q '"title":"Restore mise dot history publishing"' <<<"$objective" || fail "wrong objective: $objective"
grep -q '"project":"probe"' <<<"$objective" || fail "objective filed on the wrong board: $objective"
grep -q 'is not a directory' <<<"$objective" || fail 'the objective does not carry the observed failure'
grep -q 'Do not destroy, rewrite, or discard unpublished local checkpoints' <<<"$objective" || fail "the objective lost its constraints: $objective"
[ "$(cat "$spawn_log")" ] || fail 'the spawn was not recorded for a human'

# --- a second tick inside the cooldown neither spawns nor notifies -----------
tick 'cooldown'
[ "$(spawns)" = 1 ] || fail 'a second tick inside the cooldown spawned another run'
[ "$(notifications)" = 0 ] || fail 'a tick inside the cooldown notified the user'
[ "$(wc -l <"$log" | tr -d ' ')" = 1 ] || fail "a tick inside the cooldown added log noise: $(cat "$log")"

# --- the retry reuses the objective it already filed -------------------------
export MISE_HISTORY_REPAIR_COOLDOWN_S=0
tick 'retry'
[ "$(spawns)" = 2 ] || fail 'the retry did not spawn again after its cooldown'
[ "$(filed_id)" = "$task" ] || fail 'the retry filed a second objective instead of reusing the first'

# --- attempts spent: the user is told once, then the tick stays quiet --------
export MISE_HISTORY_REPAIR_MAX_ATTEMPTS=2
tick 'exhausted'
[ "$(notifications)" = 1 ] || fail 'spending every attempt did not notify the user'
grep -q 'cannot fix publishing-blocked automatically' "$NOTIFY_CALLS" || fail "the notification does not say what could not be fixed: $(cat "$NOTIFY_CALLS")"
grep -q 'is not a directory' "$NOTIFY_CALLS" || fail "the notification does not carry the failure: $(cat "$NOTIFY_CALLS")"
grep -q 'publishing-blocked: needs a person' "$log" || fail "the escalation was not logged: $(cat "$log")"
tick 'after the notification'
[ "$(notifications)" = 1 ] || fail 'the user was notified again for the same incident'
# --- a run that ends without repairing it and names the decision reaches the
# --- user on the next tick, without spending another attempt -----------------
reset
export MISE_HISTORY_REPAIR_MAX_ATTEMPTS=3
stalled
tick 'first attempt'
[ "$(spawns)" = 1 ] || fail 'the first attempt did not spawn'
gave_up="$(filed_id)"
"$atask" claim "$gave_up" >/dev/null || fail 'the fixture could not claim the objective'
"$atask" log --next 'Person decision required: untrack the path here, or stop the box vendoring it.' >/dev/null || fail 'the fixture could not record the decision'
"$atask" claim release >/dev/null || fail 'the fixture could not release the objective'
tick 'the run gave up'
[ "$(spawns)" = 1 ] || fail 'a run that named a decision was retried instead of reported'
[ "$(notifications)" = 1 ] || fail 'a run that named a decision never reached the user'
grep -q 'Person decision required' "$NOTIFY_CALLS" || fail "the notification does not carry the decision: $(cat "$NOTIFY_CALLS")"
grep -q 'needs a person' "$log" || fail "the escalation was not logged: $(cat "$log")"
tick 'the run gave up, second tick'
[ "$(notifications)" = 1 ] || fail 'the user was notified again for the same incident'
# --- no worker can be started at all: the user hears about it ----------------
reset
stalled
export MISE_HISTORY_REPAIR_SPAWN="$work/bin/capability-fail"
unset MISE_HISTORY_REPAIR_MAX_ATTEMPTS
tick 'unstartable run'
[ "$(notifications)" = 1 ] || fail 'a run that never started did not notify the user'
grep -q 'blocked' "$log" || fail "the blocked escalation was not logged: $(cat "$log")"
export MISE_HISTORY_REPAIR_SPAWN="$work/bin/capability-ok"
tick 'unstartable run, second tick'
[ "$(notifications)" = 1 ] || fail 'the user was notified twice for one incident'

# --- the heal tool failing is the watchdog's own tooling, and escalates too --
reset
healthy
export MISE_HISTORY_WATCHDOG_HEAL="$work/bin/heal-fail"
tick 'heal failed'
[ "$(spawns)" = 1 ] || fail 'a failing heal did not spawn a repair run'
grep -q 'Fix the mise dot encryption heal' <<<"$("$atask" show "$(filed_id)" --json)" || fail 'the heal failure filed the wrong objective'
export MISE_HISTORY_WATCHDOG_HEAL="$work/bin/heal-ok"

# --- a healthy service stays silent and clears the ledger --------------------
healthy
tick 'healthy'
[ "$(spawns)" = 1 ] || fail 'a healthy status spawned a run'
[ "$(notifications)" = 0 ] || fail 'a healthy status notified the user'
[ ! -e "$work/state" ] || fail 'a healthy tick left the attempt ledger behind'

# --- the entry points the watchdog uses directly -----------------------------
bash "$repair" --class publishing-blocked --detail 'x' --dry-run >"$work/plan" || fail 'the dry run failed'
grep -q '^title=Restore mise dot history publishing$' "$work/plan" || fail "the dry run did not print the plan: $(cat "$work/plan")"
grep -q '^proof=run: ' "$work/plan" || fail "the plan has no proof: $(cat "$work/plan")"
[ ! -e "$work/state" ] || fail 'the dry run wrote state'
[ "$(spawns)" = 1 ] || fail 'the dry run spawned a run'
if bash "$repair" --class nonsense --detail x >/dev/null 2>&1; then
	fail 'an unknown failure class was accepted'
fi
if MISE_HISTORY_REPAIR_STATE=/ bash "$repair" --clear >/dev/null 2>&1; then
	fail 'a state dir outside the tool was accepted'
fi

mkdir -p "$work/state" && : >"$work/state/repair-publishing-blocked"
MISE_HISTORY_REPAIR_STATE="$work/state" bash "$repair" --clear || fail 'the clear failed'
[ ! -e "$work/state" ] || fail 'the clear left the ledger behind'

# --- a stale history lock goes, a fresh one stays (on either OS's date) ------
reset
healthy
mkdir -p "$HOME/.local/state/mise/history"
touch -t 202001010000 "$HOME/.local/state/mise/history/sync.lock"
touch "$HOME/.local/state/mise/history/operation"
tick 'stale lock'
[ ! -e "$HOME/.local/state/mise/history/sync.lock" ] || fail 'a lock from 2020 was left in place'
[ -e "$HOME/.local/state/mise/history/operation" ] || fail 'a fresh lock was removed'
grep -q 'removed stale sync.lock' "$log" || fail "the lock removal was not logged: $(cat "$log")"
rm -f "$HOME/.local/state/mise/history/operation"

# --- a Linux fleet box: the same script, systemd for the service and the run --
reset
: >"$SYSTEMCTL_CALLS"
: >"$SYSTEMD_RUN_CALLS"
export MISE_HISTORY_WATCHDOG_OS=Linux
export XDG_STATE_HOME="$work/xdg"
unset MISE_HISTORY_LOG_DIR
linux_log="$XDG_STATE_HOME/mise-history-watchdog/mise-history-watchdog.log"
linux_spawn_log="$XDG_STATE_HOME/mise-history-watchdog/mise-history-repair.log"
stalled
tick 'linux first escalation'
[ "$(wc -l <"$SYSTEMD_RUN_CALLS" | tr -d ' ')" = 1 ] || fail "a blocked publish did not start exactly one transient unit: $(cat "$SYSTEMD_RUN_CALLS")"
[ "$(spawns)" = 0 ] || fail 'the run was started in the tick cgroup, where systemd would kill it when the tick ends'
grep -q -- '--unit=mise-history-repair-at-' "$SYSTEMD_RUN_CALLS" || fail "the run is not a named transient unit: $(cat "$SYSTEMD_RUN_CALLS")"
grep -q "StandardOutput=append:$linux_spawn_log" "$SYSTEMD_RUN_CALLS" || fail "the run does not log to the Linux state dir: $(cat "$SYSTEMD_RUN_CALLS")"
grep -q 'run start_atask_task --input {"id":"at-[a-z0-9]*","onComplete":"merge"' "$SYSTEMD_RUN_CALLS" || fail "the run is not start_atask_task: $(cat "$SYSTEMD_RUN_CALLS")"
grep -q 'publishing-blocked: spawned at-' "$linux_log" || fail "the Linux spawn was not logged under the state dir: $(cat "$linux_log" 2>&1)"
[ "$(notifications)" = 0 ] || fail 'the user was notified before any worker could try on Linux'

# A frozen watcher is restarted through systemctl, not launchctl.
printf '%s\n' '✓ 100 entries up to date (`--verbose` lists them all)' '  watcher health (updated 900s ago): last capture 2026-11-04 18:00' >"$MISE_STATUS"
: >"$SYSTEMCTL_CALLS"
tick 'linux frozen watcher'
grep -q -- '--user restart dev.mise.mise-history.service' "$SYSTEMCTL_CALLS" || fail "a frozen watcher was not restarted through systemd: $(cat "$SYSTEMCTL_CALLS")"
grep -q 'watcher health frozen 900s' "$linux_log" || fail 'the restart was not logged'

# A transient unit that cannot be created reaches the user as a plain notification.
reset
rm -rf "$XDG_STATE_HOME"
stalled
FAKE_SYSTEMD_RUN_FAIL=1 tick 'linux unstartable run'
[ "$(notifications)" = 1 ] || fail 'a run that could not be started on Linux did not notify'
if grep -q -- '^-e ' "$NOTIFY_CALLS"; then
	fail "the Linux notification used the AppleScript form: $(cat "$NOTIFY_CALLS")"
fi
grep -q 'mise history watchdog' "$NOTIFY_CALLS" || fail "the Linux notification has no title: $(cat "$NOTIFY_CALLS")"
export MISE_HISTORY_WATCHDOG_OS=Darwin
unset XDG_STATE_HOME

echo 'mise history watchdog repair: ok'
