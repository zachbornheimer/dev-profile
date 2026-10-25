#!/usr/bin/env bash
# rev: 1
# HowToCheck=Manual agent=com.microsoft.update.agent
# wrapper hash: {{ include (joinPath .chezmoi.sourceDir "dot_local/bin/executable_mau-disable") | sha256sum }}
set -euo pipefail

[[ $(uname -s) == "Darwin" ]] || { echo "disable-mau: macOS only — skipping"; exit 0; }

"$HOME/.local/bin/mau-disable"
