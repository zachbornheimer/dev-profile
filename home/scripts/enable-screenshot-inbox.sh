#!/usr/bin/env bash
# rev: 1
# plist hash: {{ include (joinPath .chezmoi.sourceDir "Library/LaunchAgents/com.zbornheimer.screenshot-inbox.plist.tmpl") | sha256sum }}
# bins hash: {{ include (joinPath .chezmoi.sourceDir "dot_local/bin/executable_sc-path") | sha256sum }}
set -euo pipefail

[[ $(uname -s) == "Darwin" ]] || {
  echo "enable-screenshot-inbox: macOS only — skipping"
  exit 0
}

readonly PROJECT="$HOME/Developer/Personal/screenshot-inbox"
readonly LABEL="com.zbornheimer.screenshot-inbox"
readonly PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
readonly DOMAIN="gui/$(id -u)"

if [[ ! -d "$PROJECT" ]]; then
  echo "enable-screenshot-inbox: project missing at $PROJECT — skipping agent load"
  echo "  clone/create the uv project, then: chezmoi apply && uv run --project \"$PROJECT\" screenshot-inbox set-capture"
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "enable-screenshot-inbox: uv not on PATH — skipping"
  exit 0
fi

mkdir -p "$HOME/Pictures/Screenshots/inbox" \
  "$HOME/Pictures/Screenshots/archive/pinned" \
  "$HOME/Pictures/Screenshots/archive/2026-pre-system" \
  "$HOME/Pictures/Screenshots/.text" \
  "$HOME/Library/Logs"

# Ensure deps + entrypoint, then point system screencapture at the inbox.
(
  cd "$PROJECT"
  uv sync --quiet
  uv run screenshot-inbox set-capture
) || {
  echo "enable-screenshot-inbox: uv sync / set-capture failed — agent not loaded"
  exit 0
}

if [[ ! -f "$PLIST" ]]; then
  echo "enable-screenshot-inbox: $PLIST missing after apply — skip load"
  exit 0
fi

launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl kickstart -k "$DOMAIN/$LABEL" 2>/dev/null || true

echo "enable-screenshot-inbox: loaded $LABEL (watch KeepAlive)"
