#!/usr/bin/env bash
# rev: 2
# shellcheck disable=SC1054,SC1073,SC1065,SC1064,SC1072,SC1036,SC1056,SC1083
# OFF by default. Does nothing unless chezmoi data `tmpdirReaper.enabled` is the boolean true.
{{- $enabled := dig "tmpdirReaper" "enabled" false . }}
# enabled: {{ $enabled }}
# plist hash: {{ include (joinPath .chezmoi.sourceDir "Library/LaunchAgents/org.zysys.tmpdir-reaper.plist.tmpl") | sha256sum }}
set -euo pipefail

{{ if not (kindIs "bool" $enabled) -}}
echo "enable-tmpdir-reaper: tmpdirReaper.enabled must be a boolean (enabled = true, not \"true\"); got '{{ printf "%v" $enabled }}'" >&2
exit 1
{{- else if not $enabled -}}
echo "enable-tmpdir-reaper: disabled (set tmpdirReaper.enabled = true in chezmoi data to enable) — skipping"
exit 0
{{- else -}}
[[ $(uname -s) == "Darwin" ]] || { echo "enable-tmpdir-reaper: macOS only — skipping"; exit 0; }

readonly LABEL="org.zysys.tmpdir-reaper"
readonly PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
domain="gui/$(id -u)"
readonly DOMAIN="$domain"

launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

echo "enable-tmpdir-reaper: loaded $LABEL"
{{- end }}
