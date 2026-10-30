#!/usr/bin/env bash
set -euo pipefail
# Edit tools/repo/shebang-scripts-executable.sh: `mise run generate` copies it into bin/.

# Shebang files get the executable bit. hk's builtin only judged; this fixer
# chmod +x's the worktree file and records 100755 in the index so the commit
# is executable. Mode-only; never rewrite bytes. Never fail.
(($#)) || exit 0
for f in "$@"; do
	[[ -f "${f}" && ! -L "${f}" ]] || continue
	IFS= read -r first <"${f}" || true
	[[ "${first}" == "#!"* ]] || continue
	chmod +x "${f}" || true
	git update-index --chmod=+x -- "${f}" || true
done
exit 0
