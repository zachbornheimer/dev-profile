#!/usr/bin/env bash
# Build Go dotfiles CLIs (Evident Output presentation) into ~/.local/lib/dotfiles-apps.
# PATH entry points are thin wrappers under ~/.local/bin (managed separately).
# Re-runs when this script's content hash changes (chezmoi run_onchange).
set -euo pipefail

home="{{ .chezmoi.homeDir }}"
dest_lib="${home}/.local/lib/dotfiles-apps"
mkdir -p "$dest_lib"

candidates=(
  "${home}/Developer/Personal/dotfiles/apps"
  "{{ .chezmoi.sourceDir }}/../apps"
  "${home}/.dotfiles/apps"
)

apps=""
for c in "${candidates[@]}"; do
  if [[ -f "${c}/go.mod" ]]; then
    apps="$c"
    break
  fi
done

if [[ -z "$apps" ]]; then
  echo "build-dotfiles-apps: no apps/ module found — skip" >&2
  exit 0
fi

if ! command -v go >/dev/null 2>&1; then
  echo "build-dotfiles-apps: go not on PATH — skip" >&2
  exit 0
fi

cmds=(
  dotfiles-capture
  dotfiles-snapshot
  dotfiles-sync
  macos-security-updates-on
  mau-disable
  op-ssh-sync
  tmpdir-reaper
  zsh-bench
)

echo "build-dotfiles-apps: building from ${apps} → ${dest_lib}"
for cmd in "${cmds[@]}"; do
  echo "  → ${dest_lib}/${cmd}"
  (cd "$apps" && go build -o "${dest_lib}/${cmd}" "./cmd/${cmd}")
  chmod +x "${dest_lib}/${cmd}"
done

echo "build-dotfiles-apps: done (${#cmds[@]} binaries)"
