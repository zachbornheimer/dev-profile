#!/usr/bin/env bash
# The host a worktree registers stays a valid DNS name: a branch name too long
# for a label keeps a 63-character host label, and a worktree of a bare clone
# named <repo>.git names its repo without the suffix.
# Usage: route-labels.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' cache='' rn=''
. "$(dirname "$0")/world.sh" "$@"

repo="${work}/${rn}"
pair_repo "${repo}"
cd "${repo}"

# A branch name too long for a DNS label keeps a 63-character host label.
long="feat/$(printf 'a%.0s' {1..80})"
git worktree add -q -b "${long}" "${work}/${rn}-long"
cd "${work}/${rn}-long"
run_dev || fail "dev in a long-branch worktree must work"
label="$(sed -n 3p "${cache}/${rn}-long.pid" | cut -d. -f1)"
((${#label} <= 63)) || fail "a worktree host label must fit in 63 characters, got ${#label}"
stop_stack "${rn}-long"
cd "${repo}"
git worktree remove --force "${work}/${rn}-long"
git worktree prune

# A bare clone named <repo>.git names its repo without the suffix.
git clone -q --bare "${repo}" "${work}/bare-home/${rn}-bare.git"
git -C "${work}/bare-home/${rn}-bare.git" worktree add -q -b feat/b "${work}/${rn}-bare-feat-b" main
cd "${work}/${rn}-bare-feat-b"
mkdir -p mise-tasks
sleeper_serve mise-tasks/dev-serve
run_dev || fail "dev in a bare repo's worktree must work"
expect "^state=running url=https://feat-b\\.${rn}-bare\\.localhost pid=[0-9]+\$"
stop_stack "${rn}-bare-feat-b"
cd "${repo}"

echo "dev-family route-labels fixture ok"
