#!/usr/bin/env bash
# rev: 1
# shellcheck disable=SC1054,SC1073,SC1065,SC1064,SC1072,SC1036,SC1056,SC1083,SC2140
# script hash: {{ include (joinPath .chezmoi.sourceDir "dot_local/bin/executable_macos-security-updates-on") | sha256sum }}
set -euo pipefail

[[ $(uname -s) == "Darwin" ]] || { echo "enable-macos-security-updates: macOS only — skipping"; exit 0; }

askpass="{{ joinPath .chezmoi.sourceDir ".." "bin" "sudo-askpass" }}"
if [[ -x "$askpass" ]]; then
  export SUDO_ASKPASS="$askpass"
fi

"$HOME/.local/bin/macos-security-updates-on"
