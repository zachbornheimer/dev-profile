#!/usr/bin/env bash
# Reconcile Homebrew packages to the manifest whenever the Brewfile changes.
# shellcheck disable=SC1054,SC1073,SC1065,SC1064,SC1072,SC1036,SC1056,SC1083,SC2140
# The hash line re-triggers this on `chezmoi apply` after any Brewfile edit;
# --no-upgrade installs what's missing without upgrading everything else.
# The Brewfile lives at the repo root (one level up from the chezmoi source).
#
# Brewfile hash: {{ include (joinPath .chezmoi.sourceDir ".." "Brewfile") | sha256sum }}
set -euo pipefail

brewfile="{{ joinPath .chezmoi.sourceDir ".." "Brewfile" }}"
if command -v brew >/dev/null 2>&1 && [ -f "$brewfile" ]; then
  brew bundle --file="$brewfile" --no-upgrade
else
  echo "run_onchange: brew or Brewfile missing — skipping package reconcile"
fi
