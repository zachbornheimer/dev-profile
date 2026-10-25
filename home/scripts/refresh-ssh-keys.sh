#!/usr/bin/env bash
# Re-mirror 1Password SSH public keys to ~/.ssh/1p whenever the agent's exposed
# vaults change. The hash line makes chezmoi re-run this on `chezmoi apply` only
# when agent.toml changes; op-ssh-sync is itself checksum-gated, so it's cheap.
# Rotating a key inside an already-exposed vault won't change agent.toml — run
# `op-ssh-sync` directly for that (it's idempotent).
#
# agent.toml hash: {{ include "dot_config/1Password/ssh/agent.toml" | sha256sum }}
set -euo pipefail

if command -v op-ssh-sync >/dev/null 2>&1 && op account get >/dev/null 2>&1; then
  op-ssh-sync
else
  echo "run_onchange: 1Password locked or op-ssh-sync absent — skipping key mirror" \
       "(run 'op-ssh-sync' once unlocked)"
fi
