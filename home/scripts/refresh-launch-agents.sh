#!/usr/bin/env bash
# rev: 1
# shellcheck disable=SC1054,SC1073,SC1065,SC1064,SC1072,SC1036,SC1056,SC1083
# Generic (re)load of every tracked user LaunchAgent. Reruns when any plist changes.
{{- range glob (joinPath .chezmoi.sourceDir "Library/LaunchAgents/*.plist.tmpl") }}
# {{ base . }}: {{ include . | sha256sum }}
{{- end }}
set -uo pipefail

[[ $(uname -s) == "Darwin" ]] || {
  echo "refresh-launch-agents: macOS only — skipping"
  exit 0
}

readonly DOMAIN="gui/$(id -u)"
readonly AGENT_DIR="$HOME/Library/LaunchAgents"

# Agents with a dedicated enable/install script own their own load; skip to avoid double-loading.
readonly -a OWNED_ELSEWHERE=(
  com.zach.brew-maintenance
  com.zach.brew-maintenance-watch
  com.zbornheimer.screenshot-inbox
  com.zbornheimer.volatile-downloads
  org.zysys.tmpdir-reaper
)

# Superseded labels: unload and delete.
readonly -a RETIRED=(
  com.zbornheimer.semgrep-stall-watchdog
)

# Tracked agents (from the chezmoi source tree).
readonly -a TRACKED=(
{{- range glob (joinPath .chezmoi.sourceDir "Library/LaunchAgents/*.plist.tmpl") }}
  {{ base . | trimSuffix ".plist.tmpl" | quote }}
{{- end }}
)

is_owned_elsewhere() {
  local label
  for label in "${OWNED_ELSEWHERE[@]}"; do
    [[ "$1" == "$label" ]] && return 0
  done
  return 1
}

is_disabled() {
  launchctl print-disabled "$DOMAIN" 2>/dev/null | grep -Fq "\"$1\" => disabled"
}

program_path() {
  plutil -extract Program raw -o - "$1" 2>/dev/null \
    || plutil -extract ProgramArguments.0 raw -o - "$1" 2>/dev/null
}

retire_agent() {
  local label="$1" plist="$AGENT_DIR/$1.plist"
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  if [[ -f "$plist" ]]; then
    rm -f "$plist"
    echo "refresh-launch-agents: retired $label"
  fi
}

refresh_agent() {
  local label="$1" plist="$AGENT_DIR/$1.plist" program
  if [[ ! -f "$plist" ]]; then
    echo "refresh-launch-agents: $label plist missing after apply — skip"
    return 0
  fi
  program="$(program_path "$plist")"
  if [[ -n "$program" && ! -e "$program" ]]; then
    echo "refresh-launch-agents: $label program missing ($program) — skip"
    return 0
  fi
  if is_disabled "$label"; then
    echo "refresh-launch-agents: $label disabled by user — leaving unloaded"
    return 0
  fi
  launchctl bootout "$DOMAIN" "$plist" 2>/dev/null || true
  if launchctl bootstrap "$DOMAIN" "$plist"; then
    launchctl enable "$DOMAIN/$label" 2>/dev/null || true
    echo "refresh-launch-agents: loaded $label"
  else
    echo "refresh-launch-agents: bootstrap failed for $label — continuing"
  fi
}

for label in "${RETIRED[@]}"; do
  retire_agent "$label"
done

for label in "${TRACKED[@]}"; do
  is_owned_elsewhere "$label" && continue
  refresh_agent "$label" || true
done

exit 0
