# OneDrive runs only on demand: start it from /Applications when work needs it,
# `onedrive-stop` when done. Microsoft's updaters are disabled with launchctl
# (gui/com.microsoft.OneDriveStandaloneUpdater, system/com.microsoft.OneDrive-
# StandaloneUpdaterDaemon, system/com.microsoft.OneDriveUpdaterDaemon), so
# Homebrew owns updates. The cask is auto_updates, so plain `brew upgrade` skips
# it; `onedrive-update` runs the greedy upgrade. The pkg's postinstall relaunches
# OneDrive and adds a login item, so the update leaves it the way it found it.

typeset -ga _onedrive_bundle_ids=(com.microsoft.OneDrive com.microsoft.SharePoint-mac)
typeset -ga _onedrive_login_items=("OneDrive" "OneDrive Sync Service")

# Quit OneDrive and its sync service; remove the login item it re-adds on every
# launch (OpenAtLogin=0 does not stop it). Quit is time-limited: with a sign-in or
# setup window open, OneDrive ignores the AppleScript quit and would hang it.
onedrive-stop() {
	emulate -L zsh
	local pattern='/Applications/OneDrive.app/Contents/' id name
	for id in $_onedrive_bundle_ids; do
		timeout 8 osascript -e "if application id \"$id\" is running then" \
			-e 'with timeout of 5 seconds' -e "tell application id \"$id\" to quit" \
			-e 'end timeout' -e 'end if' >/dev/null 2>&1
	done
	pkill -f "$pattern" 2>/dev/null
	local -i tries=6
	while pgrep -f "$pattern" >/dev/null && ((tries-- > 0)); do
		sleep 0.5
	done
	pkill -9 -f "$pattern" 2>/dev/null
	for name in $_onedrive_login_items; do
		timeout 15 osascript -e "tell application \"System Events\" to if exists login item \"$name\" then delete login item \"$name\"" >/dev/null 2>&1
	done
	if pgrep -f "$pattern" >/dev/null; then
		__ -t failed "OneDrive is still running: $(pgrep -f "$pattern" | tr '\n' ' ')"
		return 1
	fi
	__ -t success "OneDrive stopped; no OneDrive login item"
}

# Upgrade OneDrive through Homebrew, never to an older build than the one installed.
onedrive-update() {
	emulate -L zsh
	local app=/Applications/OneDrive.app installed latest
	installed=$(defaults read "$app/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null)
	latest=$(brew info --cask onedrive --json=v2 | jq -r '.casks[0].version') || return
	if [[ -n $installed && $(print -l -- "$latest" "$installed" | sort -V | tail -1) == "$installed" ]]; then
		__ -t success "OneDrive $installed is current (Homebrew offers $latest)"
		return 0
	fi
	local -i was_running=0
	pgrep -f "$app/Contents/" >/dev/null && was_running=1
	brew upgrade --cask --greedy onedrive || return
	if ((was_running)); then
		local name
		for name in $_onedrive_login_items; do
			osascript -e "tell application \"System Events\" to if exists login item \"$name\" then delete login item \"$name\"" >/dev/null 2>&1
		done
		__ -t success "OneDrive updated to $latest; left running"
	else
		onedrive-stop && __ -t success "OneDrive updated to $latest"
	fi
}
