# gh via ghx: rate-limit-aware wrapper (~/Developer/Personal/ghx).
# ghx resolves the real gh binary via PATH, so this alias cannot recurse.
alias gh='ghx'
alias gs='git status --short --branch'
alias gcm='git commit -m'
alias gco='git checkout'
alias gp='git pull --ff-only'
alias gpu='git push'
# PR Workflow
alias prl='gh pr list'
alias prv='gh pr view --web'
alias prc='gh pr checkout'
# Smart Git
alias gco-='git checkout -'
alias gcam='git commit -a --amend --no-edit'
alias gcp='git cherry-pick'
alias gca='git commit -a'

# repo-retire (Go): ~/Developer/Personal/repo-retire → go build -o ~/.local/bin/repo-retire
# Retire local clones from disk when safe (Developer hygiene; no orphans).
#   repo-retire check|salvage [path]
#   repo-retire [--allow-ignored] [--yes BASENAME] [path]
# del-repo is a deprecated shim → repo-retire

repo-reports() {
	local script="$HOME/Developer/Personal/scripts/python/repo-status-report.py"
	local gh_cmd="${GH_CMD:-gh}"
	local min="${REPO_REPORTS_MIN:-100}" # refuse to start below this many core calls

	# 1. script present and readable?
	if [[ ! -r "$script" ]]; then
		__ -t failed "repo-reports: script not found (or unreadable) at $script"
		return 1
	fi

	# 2. does the CLI have quota? (the rate_limit endpoint itself is free)
	local remaining reset
	read -r remaining reset < <(
		"$gh_cmd" api rate_limit -q '.resources.core | "\(.remaining) \(.reset)"' 2>/dev/null
	)
	if [[ -z "$remaining" ]]; then
		__ -t failed "repo-reports: couldn't read rate limit via '$gh_cmd' — is it installed and authenticated?"
		return 1
	fi
	if ((remaining < min)); then
		__ -t failed "repo-reports: only $remaining core API calls left (need ≥ $min); resets at $(date -r "$reset" '+%H:%M')"
		return 1
	fi

	# 3. run it
	local d
	d=$(date +%y-%m-%d)
	local src="${1:-$gh_cmd api --paginate user/orgs -q .[].login}" # override the login source if you like
	eval "$src" | GH_CMD="$gh_cmd" xargs -P4 -I{} sh -c \
		'uv run -- "'"$script"'" "$1" --format md > "/tmp/'"$d"'-$1.md"' _ {}
	__ -t success "repo-reports: wrote /tmp/$d-*.md" >&2
}

gclone() {
	git clone "$1" && cd "$(basename "$1" .git)"
}

# ── git push --fix ──────────────────────────────────────────────────────────
# `git push --fix` pushes normally. If the push fails, it runs `hk fix`, retries
# once, and if the push still fails it launches Pi in the repo with a prompt
# built from the failure log. Override these in ~/.zshrc.local, not in the body.
#
#   GIT_PUSH_FIX_PI_CMD   program to launch                     (default: pi)
#   GIT_PUSH_FIX_PI_ARGS  array of Pi args                      (default below)
#   GIT_PUSH_FIX_PROMPT   function that builds the prompt       (default below)
#   GIT_PUSH_FIX_MASTRA   skill file named in the prompt        (default below)
typeset -g GIT_PUSH_FIX_PI_CMD="${GIT_PUSH_FIX_PI_CMD:-pi}"
typeset -g GIT_PUSH_FIX_PROMPT="${GIT_PUSH_FIX_PROMPT:-_git_push_fix_prompt}"
typeset -g GIT_PUSH_FIX_MASTRA="${GIT_PUSH_FIX_MASTRA:-$HOME/.agents/available-skills/mastra/SKILL.md}"
if ((!${+GIT_PUSH_FIX_PI_ARGS})); then
	typeset -ga GIT_PUSH_FIX_PI_ARGS=(--model sonnet:high)
fi

_git_push_fix_prompt() {
	local log=$1 branch
	branch=$(command git rev-parse --abbrev-ref HEAD 2>/dev/null)
	cat <<-EOF
		\`git push\` failed in $PWD on branch ${branch:-unknown}.
		I already ran \`hk fix\` and retried the push; it still fails.

		Use the mastra skill at $GIT_PUSH_FIX_MASTRA to diagnose the failure.
		Read the full log at $log, fix the root cause, then run \`hk fix\` and
		\`hk check\` until they pass. Do not run \`git push\`; report what changed.
	EOF
}

git() {
	if [[ $1 != push ]] || ((!${@[(I)--fix]})); then
		command git "$@"
		return
	fi

	local -a args
	local arg log
	for arg in "${@[2,-1]}"; do
		[[ $arg == --fix ]] && continue
		args+=("$arg")
	done

	log=$(mktemp -t git-push-fix)
	command git push "${args[@]}" 2>&1 | tee "$log"
	local push_status=${pipestatus[1]}
	if ((!push_status)); then
		__ -t success "git push --fix: push succeeded" >&2
		rm -f "$log"
		return 0
	fi

	if ((${+commands[hk]})); then
		__ -t warn "git push --fix: push failed, running hk fix"
		command hk fix 2>&1 | tee -a "$log"
		command git push "${args[@]}" 2>&1 | tee -a "$log"
		push_status=${pipestatus[1]}
		if ((!push_status)); then
			__ -t success "git push --fix: hk fix cleared it, push succeeded" >&2
			rm -f "$log"
			return 0
		fi
	else
		__ -t warn "git push --fix: hk not found, skipping auto-fix"
	fi

	__ -t warn "git push --fix: still failing, launching ${GIT_PUSH_FIX_PI_CMD}"$'\n'"  failure log: $log"
	"${GIT_PUSH_FIX_PI_CMD}" "${GIT_PUSH_FIX_PI_ARGS[@]}" "$(${GIT_PUSH_FIX_PROMPT} "$log")"
}
