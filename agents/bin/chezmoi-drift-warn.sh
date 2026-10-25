#!/bin/sh
# chezmoi-drift-warn.sh — SessionStart-hook-shaped facade over
# chezmoi-drift.sh: a cheap (single `chezmoi diff`, no per-file mtime
# classification) check for "does ~/.agents or ~/.claude currently
# differ from the chezmoi source at all". Non-zero means a later
# `chezmoi apply` would change something under live — could be a
# pending, expected source-ahead update, or an unlanded live edit about
# to be silently reverted. Prints additionalContext pointing at the
# full audit; never blocks (always exits 0), per the ZYS-729 lesson
# that a drift check must warn, not gate, a session. On any tool
# failure it logs via hc_log and exits clean rather than surfacing an
# error on every session start.
#
# Usage: chezmoi-drift-warn.sh
set -u

SELF_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=../hooks/hook-common.sh disable=SC1091
. "$SELF_DIR/../hooks/hook-common.sh"

AUDIT_ROOTS="$HOME/.agents $HOME/.claude"
HOOK_NAME=chezmoi-drift-warn

if ! command -v chezmoi >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
  hc_log "$HOOK_NAME" allow "chezmoi-or-jq-missing"
  exit 0
fi

# shellcheck disable=SC2086
diff_output=$(chezmoi diff -r $AUDIT_ROOTS 2>&1)
diff_status=$?
if [ "$diff_status" -ne 0 ]; then
  hc_log "$HOOK_NAME" allow "chezmoi-diff-failed-exit-${diff_status}"
  exit 0
fi

differing_count=$(printf '%s\n' "$diff_output" | grep -c '^diff --git')

[ "$differing_count" -gt 0 ] 2>/dev/null || exit 0

message="chezmoi-drift: $differing_count file(s) differ between the live ~/.agents or ~/.claude tree and the chezmoi source. Run \`~/.agents/bin/chezmoi-drift.sh --report\` before a \`chezmoi apply\` — it may revert an unlanded edit."

jq -n --arg ctx "$message" \
  '{hookSpecificOutput:{hookEventName:"SessionStart", additionalContext:$ctx}}' 2>/dev/null ||
  printf '%s\n' "$message"

exit 0
