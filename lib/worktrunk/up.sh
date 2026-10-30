# shellcheck shell=sh
git fetch --all --prune
wt step for-each -- sh -c '
  git rev-parse --verify -q @{u} >/dev/null || exit 0
  g=$(git rev-parse --git-dir)
  rebasing() { test -d "$g/rebase-merge" || test -d "$g/rebase-apply"; }
  rebasing && exit 0
  git diff --quiet HEAD || { git merge --ff-only --no-autostash @{u}; exit 0; }
  git rebase @{u} --no-autostash || { rebasing || exit 0; git rebase --abort; }
'
