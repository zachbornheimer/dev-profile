# ── GitHub ───────────────────────────────────────────────────────────────────
# ghx is a rate-limit-aware wrapper around gh.
alias gh='ghx'

# ── Git Aliases ───────────────────────────────────────────────────────────────
alias gs='git status --short --branch'
alias gcm='git commit -m'
alias gco='git checkout'
alias gco-='git checkout -'
alias gcam='git commit -a --amend --no-edit'
alias gca='git commit -a'
alias gcp='git cherry-pick'
alias gp='git pull --ff-only'
alias gpu='git push'

# ── Pull Requests ────────────────────────────────────────────────────────────
alias prl='gh pr list'
alias prv='gh pr view --web'
alias prc='gh pr checkout'

# ── Repository Utilities ─────────────────────────────────────────────────────
# Clone a repository and enter its directory.
gclone() {
	[[ $# -eq 1 ]] || {
		print -u2 -- 'Usage: gclone <repository>'
		return 2
	}

	command git clone -- "$1" || return
	builtin cd -- "$(basename "$1" .git)"
}

# repo-retire: ~/Developer/Personal/repo-retire
# Build: go build -o ~/.local/bin/repo-retire
#   repo-retire check|salvage [path]
#   repo-retire [--allow-ignored] [--yes BASENAME] [path]
# del-repo is a deprecated shim.

# ── Repository Reports ───────────────────────────────────────────────────────
# Generate organization reports when sufficient GitHub API quota remains.
# An optional argument overrides the organization source command (trusted input).
repo-reports() {
	emulate -L zsh

	local script="$HOME/Developer/Personal/scripts/python/repo-status-report.py"
	local gh_cmd="${GH_CMD:-ghx}"
	local min="${REPO_REPORTS_MIN:-100}"
	local remaining reset date_tag

	# 1. Validate prerequisites.
	if [[ ! -r "$script" ]]; then
		__ -t failed "repo-reports: script missing or unreadable: $script"
		return 1
	fi

	if [[ "$min" != <-> ]]; then
		__ -t failed "repo-reports: REPO_REPORTS_MIN must be a nonnegative integer"
		return 1
	fi

	# 2. Check API quota (the rate_limit endpoint is free).
	read -r remaining reset < <(
		"$gh_cmd" api rate_limit \
			-q '.resources.core | "\(.remaining) \(.reset)"' 2>/dev/null
	)

	if [[ "$remaining" != <-> || "$reset" != <-> ]]; then
		__ -t failed "repo-reports: cannot read GitHub API quota via $gh_cmd"
		return 1
	fi

	if ((remaining < min)); then
		__ -t failed "repo-reports: $remaining calls left (need $min); resets at $(date -r "$reset" '+%H:%M')"
		return 1
	fi

	# 3. Generate reports concurrently, preserving the optional source override.
	date_tag=$(date +%y-%m-%d)

	{
		if (($#)); then
			eval "$1"
		else
			"$gh_cmd" api --paginate user/orgs -q '.[].login'
		fi
	} | GH_CMD="$gh_cmd" xargs -P4 -I{} sh -c '
        uv run -- "$1" "$2" --format md > "/tmp/$3-$2.md"
    ' _ "$script" "{}" "$date_tag"

	local -a results=("${pipestatus[@]}")

	if ((results[1] != 0 || results[2] != 0)); then
		__ -t failed "repo-reports: report generation failed"
		return 1
	fi

	__ -o stderr -t success "repo-reports: wrote /tmp/$date_tag-*.md"
}

# ── Self-Healing Git ─────────────────────────────────────────────────────────
# Automatically repair failed push/pull commands using OMP.
#
# Workflow:
#   1. Run Git normally.
#   2. On failure, capture the error and invoke OMP.
#   3. Retry once if OMP succeeds without changing HEAD or working-tree status.
#
# Safety:
#   - Interactive shells only.
#   - No automatic commits or history rewrites.
#   - No retry when OMP changes the working tree.
#   - Temporary logs are removed on exit.
#
# Configuration:
#   GIT_REPAIR_MODEL=@task
#   GIT_REPAIR_ENABLED=1

_git_repair() (
	emulate -L zsh

	local log status head_before head_after
	local worktree_before worktree_after
	local -a quoted_args

	# 1. Capture the original Git result.
	log=$(mktemp "${TMPDIR:-/tmp}/git-repair.XXXXXXXX") || return 1
	trap 'rm -f -- "$log"' EXIT

	command git "$@" 2>&1 | tee "$log"
	status=${pipestatus[1]}

	((status == 0)) && return 0

	# 2. Preserve the original failure when OMP is unavailable.
	if ((!$+commands[omp])); then
		print -u2 -- "git repair: omp not found"
		return "$status"
	fi

	# 3. Record repository state before AI-assisted repair.
	head_before=$(command git rev-parse HEAD 2>/dev/null) || return "$status"
	worktree_before=$(command git status --porcelain=v1 --untracked-files=all) ||
		return "$status"

	# 4. Build a safely quoted command description.
	quoted_args=("${(@q)argv}")
	local git_cmd="git ${(j: :)quoted_args}"

	# 5. Delegate diagnosis and repair to OMP.
	print -u2 -- "git repair: invoking OMP..."

	omp --model "${GIT_REPAIR_MODEL:-@task}" -p \
		"$git_cmd failed (exit $status). Read $log. Diagnose and fix the root cause with minimal changes. Run relevant checks. Do not push, pull, commit, reset, rebase, force, or rewrite history. Report blockers." ||
		return "$status"

	# 6. Avoid retrying when the repair requires review or a new commit.
	head_after=$(command git rev-parse HEAD 2>/dev/null) || return "$status"
	worktree_after=$(command git status --porcelain=v1 --untracked-files=all) ||
		return "$status"

	if [[ "$head_before" != "$head_after" ||
		"$worktree_before" != "$worktree_after" ]]; then
		print -u2 -- "git repair: repository changed; review before retrying"
		return "$status"
	fi

	# 7. Retry exactly once and return Git's exit status.
	print -u2 -- "git repair: retrying..."
	command git "$@"
)

# ── Git Dispatcher ───────────────────────────────────────────────────────────
# Intercept interactive push/pull only; delegate everything else to Git.
git() {
	case "$1" in
	push | pull)
		if [[ -o interactive && -t 0 && -t 1 &&
			"${GIT_REPAIR_ENABLED:-1}" == 1 ]]; then
			_git_repair "$@"
		else
			command git "$@"
		fi
		;;
	*)
		command git "$@"
		;;
	esac
}
