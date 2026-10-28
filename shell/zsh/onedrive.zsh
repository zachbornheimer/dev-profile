# OneDrive runs only on demand: start it from /Applications when work needs it,
# `onedrive-stop` when done. Microsoft's updaters are disabled with launchctl
# (labels below), so Homebrew owns updates. The cask is auto_updates, so plain
# `brew upgrade` skips it; `onedrive-update` runs the greedy upgrade. The pkg's
# postinstall relaunches OneDrive and adds a login item, so the update leaves it
# the way it found it and confirms the updaters are still disabled.

typeset -ga _onedrive_bundle_ids=(com.microsoft.OneDrive com.microsoft.SharePoint-mac)
typeset -ga _onedrive_login_items=("OneDrive" "OneDrive Sync Service")
typeset -ga _onedrive_updater_labels=(
	gui/$UID/com.microsoft.OneDriveStandaloneUpdater
	system/com.microsoft.OneDriveStandaloneUpdaterDaemon
	system/com.microsoft.OneDriveUpdaterDaemon
)
# Anchored: matches processes executing from the bundle, not shells whose
# command line merely mentions the path.
typeset -g _onedrive_pattern='^/Applications/OneDrive\.app/Contents/'

# Delete OneDrive's login items in one System Events call, then report any that
# survived. OneDrive re-adds "OneDrive Sync Service" at some point while it runs,
# despite OpenAtLogin=0.
_onedrive_drop_login_items() {
	emulate -L zsh
	local names=${(j:", ":)_onedrive_login_items} left
	left=$(timeout 20 osascript -e 'tell application "System Events"' \
		-e "set wanted to {\"$names\"}" \
		-e 'repeat with n in wanted' \
		-e 'if exists login item (n as text) then delete login item (n as text)' \
		-e 'end repeat' \
		-e 'set remaining to {}' \
		-e 'repeat with n in wanted' \
		-e 'if exists login item (n as text) then set end of remaining to (n as text)' \
		-e 'end repeat' -e 'return remaining' -e 'end tell' 2>/dev/null) || {
		__ -t failed "Could not check OneDrive login items (System Events did not answer in 20s)"
		return 1
	}
	[[ -z $left ]] && return 0
	__ -t failed "OneDrive login item still present: $left"
	return 1
}

# Warn when a Homebrew pkg install re-enabled one of Microsoft's updaters.
_onedrive_check_updaters() {
	emulate -L zsh
	local disabled label name
	local -a bad
	disabled="$(
		launchctl print-disabled gui/$UID 2>/dev/null
		launchctl print-disabled system 2>/dev/null
	)"
	for label in $_onedrive_updater_labels; do
		name=${label:t}
		[[ $disabled == *"\"$name\" => disabled"* ]] || bad+=($label)
	done
	(($#bad)) || return 0
	for label in $bad; do
		if [[ $label == system/* ]]; then
			__ -t warn "Re-enabled: $label — fix: SUDO_ASKPASS=~/Developer/Personal/dotfiles/bin/sudo-askpass sudo -A launchctl disable $label"
		else
			__ -t warn "Re-enabled: $label — fix: launchctl disable $label"
		fi
	done
	return 1
}

# Quit OneDrive and its sync service, gracefully first: a quit request returns
# before OneDrive finishes flushing sync state. TERM, then KILL, only if it stays.
onedrive-stop() {
	emulate -L zsh
	setopt no_monitor no_notify
	local id stage=graceful
	local -i i
	pgrep -f "$_onedrive_pattern" >/dev/null || stage="was not running"
	for id in $_onedrive_bundle_ids; do
		timeout 8 osascript -e "if application id \"$id\" is running then" \
			-e 'with timeout of 5 seconds' -e "tell application id \"$id\" to quit" \
			-e 'end timeout' -e 'end if' >/dev/null 2>&1 &
	done
	wait
	for ((i = 0; i < 30; i++)); do
		pgrep -f "$_onedrive_pattern" >/dev/null || break
		sleep 0.5
	done
	if pgrep -f "$_onedrive_pattern" >/dev/null; then
		stage=TERM
		pkill -f "$_onedrive_pattern"
		for ((i = 0; i < 10; i++)); do
			pgrep -f "$_onedrive_pattern" >/dev/null || break
			sleep 0.5
		done
	fi
	if pgrep -f "$_onedrive_pattern" >/dev/null; then
		stage=KILL
		pkill -9 -f "$_onedrive_pattern"
		sleep 0.5
	fi
	local -i items_ok=1
	_onedrive_drop_login_items || items_ok=0
	if pgrep -f "$_onedrive_pattern" >/dev/null; then
		__ -t failed "OneDrive is still running: $(pgrep -f "$_onedrive_pattern" | tr '\n' ' ')"
		return 1
	fi
	((items_ok)) || return 1
	__ -t success "OneDrive stopped ($stage); no OneDrive login item"
}

# Upgrade OneDrive through Homebrew, never to an older build than the one installed.
onedrive-update() {
	emulate -L zsh
	local app=/Applications/OneDrive.app installed latest
	installed=$(defaults read "$app/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null)
	latest=$(brew info --cask onedrive --json=v2 | jq -r '.casks[0].version') || return
	if [[ -n $installed && $(print -l -- "$latest" "$installed" | sort -V | tail -1) == "$installed" ]]; then
		__ -t success "OneDrive $installed is current (Homebrew offers $latest)"
		_onedrive_check_updaters
		return
	fi
	local -i was_running=0
	pgrep -f "$_onedrive_pattern" >/dev/null && was_running=1
	brew upgrade --cask --greedy onedrive || return
	if ((was_running)); then
		_onedrive_drop_login_items || return
	else
		onedrive-stop || return
	fi
	_onedrive_check_updaters || return
	__ -t success "OneDrive updated to $latest; $( ((was_running)) && print 'left running' || print 'stopped')"
}
