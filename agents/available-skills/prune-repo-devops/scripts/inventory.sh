#!/usr/bin/env bash
# Report every devops artifact in a repo with a verdict hint.
# Usage: inventory.sh [repo-path]   Output: <verdict-hint> <path-or-pattern> <why>
set -euo pipefail

repo="${1:-.}"
cd "$repo"

found=0
tracked="$(git ls-files 2>/dev/null || true)"
[[ -n "$tracked" ]] || tracked="$(fd --type f --hidden --exclude .git --exclude target --exclude node_modules . 2>/dev/null || true)"

emit() {
	found=1
	printf '%s %s %s\n' "$1" "$2" "$3"
}

# matching <extended-regex> -> tracked paths (one per line)
matching() { printf '%s\n' "$tracked" | rg -e "$1" || true; }

report_matches() { # verdict regex why
	local path
	while IFS= read -r path; do
		[[ -n "$path" ]] && emit "$1" "$path" "$3"
	done < <(matching "$2")
}

report_matches DELETE-RETIRED '^lefthook\.ya?ml$|^\.lefthook' 'hooks are global (hk); lefthook doubles them'
report_matches DELETE-RETIRED '^\.trunk/' 'trunk retired; profile owns lint/format'
report_matches DELETE-RETIRED '^\.husky/' 'husky retired; hooks are global (hk)'
report_matches DELETE-RETIRED '^\.pre-commit-config\.yaml$' 'pre-commit retired; hooks are global (hk)'
report_matches DELETE-RETIRED '(^|/)renovate\.json5?$' 'Renovate runs from the profile; per-repo config needs justification'
report_matches DELETE-RETIRED '^\.github/dependabot\.ya?ml$' 'dependency updates come from the profile/org'
report_matches DELETE-RETIRED '^\.gate\.yaml$' 'gate retired; mise run ci is the gate'
report_matches REPLACE-WITH-MISE '(^|/)(Makefile|GNUmakefile)$|(^|/)mk/.*\.mk$|\.mk$' 'make is not the task runner; port targets to mise tasks'
report_matches DELETE-ROOT-COVERS '^(\.editorconfig|\.golangci\.ya?ml|\.prettierrc.*|buf\.work\.yaml|pnpm-workspace\.yaml)$' 'root copy exists in the profile; verify superset then delete'
report_matches KEEP-REVIEW '^scripts/' 'script: duplicates setup/lint/test/scan/doctor/ci? port to mise-tasks/ or delete'

# Workflows and composite actions: trigger names only.
while IFS= read -r wf; do
	[[ -n "$wf" ]] || continue
	triggers="$(rg -N -o '^on:\s*\[?([a-z_, -]+)\]?' -r '$1' "$wf" 2>/dev/null | tr -s ' \n' ' ' || true)"
	if [[ -z "${triggers// /}" ]]; then
		triggers="$(rg -N -U -o '(?m)^on:\n((?:  [a-z_]+:.*\n|    .*\n|\s*\n)+)' -r '$1' "$wf" 2>/dev/null | rg -o '^  ([a-z_]+):' -r '$1' | tr '\n' ' ' || true)"
	fi
	emit KEEP-REVIEW "$wf" "workflow; triggers: ${triggers:-unknown}; CI should be profile-driven, check each job"
done < <(matching '^\.github/workflows/.*\.ya?ml$')
report_matches KEEP-REVIEW '^\.github/actions/.*/action\.ya?ml$' 'composite action: unused or duplicated by the profile?'

# mise.toml tasks: COPY vs EXTEND.
if [[ -f mise.toml ]]; then
	for verb in setup fmt lint test scan doctor ci build typecheck; do
		rg -q "^\[tasks\.\"?${verb}\"?\]" mise.toml || continue
		block="$(awk -v v="$verb" '
      $0 ~ "^\\[tasks\\.\"?" v "\"?\\]" {on=1; next}
      /^\[/ {on=0}
      on {print}' mise.toml)"
		if printf '%s\n' "$block" | rg -q "profile:${verb}"; then
			emit EXTEND-PROFILE "mise.toml:tasks.${verb}" "EXTEND: depends on profile:${verb}"
		else
			emit KEEP-REVIEW "mise.toml:tasks.${verb}" "COPY: does not depend on profile:${verb}; delete if root provides it, else extend"
		fi
	done
fi

# Stale tooling mentions (docs, configs, scripts).
while IFS= read -r hit; do
	[[ -n "$hit" ]] && emit KEEP-REVIEW "$hit" "stale tooling mention (trunk/lefthook/gate/renovate)"
done < <(rg -n -i -w --no-heading --max-count 3 -g '!references/prune-playbook.md' -g '!Cargo.lock' -g '!*.lock' -g '!target' \
  -e 'trunk' -e 'lefthook' -e 'renovate' -e '\.gate\.yaml' . 2>/dev/null | cut -c1-120 | head -20 || true)

((found)) || echo 'clean: nothing to prune'
exit 0
