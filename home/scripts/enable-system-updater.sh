#!/usr/bin/env bash
# rev: 1
# plist hash: {{ include (joinPath .chezmoi.sourceDir "Library/LaunchAgents/com.zach.system-updater.plist.tmpl") | sha256sum }}
set -euo pipefail

[[ $(uname -s) == "Darwin" ]] || { echo "enable-system-updater: macOS only — skipping"; exit 0; }

readonly LABEL="com.zach.system-updater"
readonly PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
domain="gui/$(id -u)"
readonly DOMAIN="$domain"

mkdir -p "$HOME/Library/Logs/Homebrew"

# Full pass at 02:00, then every 4 hours until a pass finds nothing
# installable. Bootout+bootstrap only this agent so a plist-only edit
# never cycles it in the minutes right before 02:00.
launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

echo "enable-system-updater: loaded $LABEL"

# Retire leftover brew-maintenance agents from the previous label.
readonly OLD_PLIST="$HOME/Library/LaunchAgents/com.zach.brew-maintenance.plist"
readonly WATCH_PLIST="$HOME/Library/LaunchAgents/com.zach.brew-maintenance-watch.plist"
launchctl bootout "$DOMAIN" "$OLD_PLIST" 2>/dev/null || true
rm -f "$OLD_PLIST"
launchctl bootout "$DOMAIN" "$WATCH_PLIST" 2>/dev/null || true
rm -f "$WATCH_PLIST"
