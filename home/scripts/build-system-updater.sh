#!/usr/bin/env bash
# Build standalone system-updater into ~/.local/lib/dotfiles-apps.
# PATH entry point is the thin wrapper under ~/.local/bin (managed separately).
# Re-runs when this script's content hash changes (chezmoi run_onchange).
set -euo pipefail

[[ $(uname -s) == "Darwin" ]] || {
  echo "build-system-updater: macOS only — skipping"
  exit 0
}

home="{{ .chezmoi.homeDir }}"
preferred="${home}/Developer/Personal/system-updater"
legacy="${home}/Developer/Personal/brew-maintenance"
if [[ -d "${preferred}" ]]; then
  src="${preferred}"
else
  src="${legacy}"
fi
dest="${home}/.local/lib/dotfiles-apps/system-updater"

if [[ ! -f "${src}/go.mod" ]]; then
  echo "build-system-updater: ${src} missing — skip" >&2
  exit 0
fi

if ! command -v go >/dev/null 2>&1; then
  echo "build-system-updater: go not on PATH — skip" >&2
  exit 0
fi

mkdir -p "$(dirname "$dest")"
echo "build-system-updater: building from ${src} → ${dest}"
(cd "$src" && go build -o "$dest" "./cmd/system-updater")
chmod +x "$dest"
echo "build-system-updater: done"
