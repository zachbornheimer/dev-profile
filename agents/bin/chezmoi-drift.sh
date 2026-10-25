#!/bin/sh
# chezmoi-drift.sh — audits ~/.agents and ~/.claude for drift between the
# live tree and the chezmoi source (~/Developer/Personal/dotfiles).
#
# CLAUDE.md tells agents to edit the live path and run `chezmoi re-add`.
# When that second step is skipped, a later `chezmoi apply` silently
# reverts the unlanded edit ("live ahead" below) — this is the dangerous
# case. This script never mutates anything; it only reports.
#
# Usage: chezmoi-drift.sh --report
set -u

SELF_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=../hooks/hook-common.sh disable=SC1091
. "$SELF_DIR/../hooks/hook-common.sh"

AUDIT_ROOTS="$HOME/.agents $HOME/.claude"

# ~/.claude is Claude Code's whole runtime home (caches, job clones, a
# multi-GB history.jsonl, daemons) — chezmoi manages only a narrow slice
# of it (.claude itself, .claude/agents, .claude/rules). Scanning the
# full tree for "untracked live" files would walk tens of thousands of
# irrelevant runtime files. Instead, untracked-live detection only looks
# inside directories that already contain at least one chezmoi-managed
# file — exactly the directories where a forgotten `chezmoi add` would
# leave a sibling file behind.
NOISE_RE='(^|/)\.DS_Store$'

command -v chezmoi >/dev/null 2>&1 || {
  echo "chezmoi-drift: chezmoi not on PATH" >&2
  exit 1
}
hc_has_jq || {
  echo "chezmoi-drift: jq not on PATH" >&2
  exit 1
}

# drift_managed_pairs_tsv — one "<live-absolute><TAB><source-absolute>"
# line per chezmoi-managed file/symlink under the audit roots. A single
# `chezmoi managed` call, not one process per file — the earlier
# per-file `chezmoi source-path`/`chezmoi diff` design took over two
# minutes against ~600 managed entries.
drift_managed_pairs_tsv() {
  # shellcheck disable=SC2086
  chezmoi managed --include=files,symlinks -p all -f json $AUDIT_ROOTS 2>/dev/null |
    jq -r 'to_entries[] | [.value.absolute, .value.sourceAbsolute] | @tsv'
}

# drift_differing_live_paths — absolute live paths chezmoi reports as
# differing from source, via one bulk `chezmoi diff`, not one per file.
drift_differing_live_paths() {
  # shellcheck disable=SC2086
  chezmoi diff -r $AUDIT_ROOTS 2>/dev/null |
    sed -n 's|^diff --git a/\(.*\) b/.*|\1|p' |
    while IFS= read -r rel; do
      echo "$HOME/$rel"
    done
}

drift_classify_managed() {
  differs_tmp="$1"
  live_path="$2"
  src_path="$3"

  if [ ! -e "$live_path" ]; then
    echo "orphan-source|$live_path"
    return 0
  fi

  grep -qxF "$live_path" "$differs_tmp" || {
    echo "in-sync|$live_path"
    return 0
  }

  live_mtime=$(hc_file_mtime "$live_path")
  src_mtime=$(hc_file_mtime "$src_path")
  case "$live_mtime,$src_mtime" in
  *[!0-9,]* | ",*" | *",")
    echo "differs-unknown-direction|$live_path"
    ;;
  *)
    if [ "$live_mtime" -gt "$src_mtime" ]; then
      echo "live-ahead|$live_path"
    else
      echo "source-ahead|$live_path"
    fi
    ;;
  esac
}

# drift_untracked_live_paths <managed-live-paths-file> — live files that
# chezmoi does not manage, in any directory that has >=1 managed file
# (see NOISE_RE comment above for why the scan isn't the whole home tree).
drift_untracked_live_paths() {
  managed_file="$1"
  managed_dirs_tmp=$(mktemp)
  sed 's|/[^/]*$||' "$managed_file" | sort -u >"$managed_dirs_tmp"

  while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    find "$dir" -maxdepth 1 -type f 2>/dev/null
  done <"$managed_dirs_tmp" | while IFS= read -r f; do
    printf '%s\n' "$f" | grep -Eq "$NOISE_RE" && continue
    grep -qxF "$f" "$managed_file" || echo "untracked-live|$f"
  done

  rm -f "$managed_dirs_tmp"
}

drift_report() {
  pairs_tmp=$(mktemp)
  differs_tmp=$(mktemp)
  managed_live_tmp=$(mktemp)
  trap 'rm -f "$pairs_tmp" "$differs_tmp" "$managed_live_tmp"' EXIT

  drift_managed_pairs_tsv >"$pairs_tmp"
  cut -f1 "$pairs_tmp" >"$managed_live_tmp"
  drift_differing_live_paths >"$differs_tmp"

  while IFS="$(printf '\t')" read -r live_path src_path; do
    [ -n "$live_path" ] || continue
    drift_classify_managed "$differs_tmp" "$live_path" "$src_path"
  done <"$pairs_tmp"

  drift_untracked_live_paths "$managed_live_tmp"
}

drift_print_report() {
  results=$(drift_report)

  for class in live-ahead source-ahead orphan-source untracked-live differs-unknown-direction in-sync; do
    rows=$(printf '%s\n' "$results" | awk -F'|' -v c="$class" '$1==c')
    [ -n "$rows" ] || continue
    count=$(printf '%s\n' "$rows" | grep -c '^')
    echo "== $class ($count) =="
    printf '%s\n' "$rows" | cut -d'|' -f2- | sed 's/^/  /'
  done
}

case "${1:-}" in
--report)
  drift_print_report
  exit 0
  ;;
*)
  echo "usage: chezmoi-drift.sh --report" >&2
  exit 2
  ;;
esac
