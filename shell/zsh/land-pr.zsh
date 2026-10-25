land-open-prs() {
	if ! git rev-parse --is-inside-work-tree &>/dev/null; then
		__ -t failed "land-open-prs: not inside a git repo"
		return 1
	fi
	if ! command -v tmux &>/dev/null; then
		__ -t failed "land-open-prs: tmux not found (brew install tmux)"
		return 1
	fi

	local repo_dir remotes session prompt
	repo_dir=$(git rev-parse --show-toplevel)
	remotes=$(git remote -v | perl -ple 's/\s+.*//' | sort -u | paste -sd, -)
	session="land-prs-$(basename "$repo_dir")"

	if tmux has-session -t "$session" 2>/dev/null; then
		__ -t failed "land-open-prs: session '$session' already running — attach with: tmux attach -t $session"
		return 1
	fi

	prompt="Use the execution-process skill to run /land-open-prs for the current repo (.) covering remotes: $remotes. You are running headlessly and unattended: never ask a clarifying question or wait for input — pick the most reasonable option and proceed, noting the assumption in your final report. Stay within this repo only; do not touch any other repo or worktree."

	local jq_filter='
		if .type=="assistant" then
			(.message.content[]? |
				if .type=="text" then .text
				elif .type=="tool_use" then "\n[tool] " + .name + ": " + (.input | tostring)
				else empty end)
		elif .type=="result" then
			"\n[done] " + (.result // .subtype // "")
		else empty end'

	tmux new-session -d -s "$session" -c "$repo_dir" \
		"claude -p --dangerously-skip-permissions --model sonnet --name '$session' --output-format stream-json --verbose '$prompt' | jq --unbuffered -r '$jq_filter'; echo; echo '--- land-open-prs finished, press enter to close ---'; read"

	__ "land-open-prs: running in tmux session '$session' — attach with: tmux attach -t $session"
}

# land-pr --org ORG --repo REPO --pr N
# land-pr owner/repo#N
# Clone that pull request under /tmp/land-pr, trust its mise config, and
# leave Copilot `/pr automerge` running in an interactive aoe session.
# Each run gets its own uuid-suffixed checkout and aoe session, so concurrent or
# repeated runs on the same PR don't collide.
# The session stays open, running successive passes of work until the PR merges or closes.
# Software-Automation-Holdings is the local folder name; GitHub's org is
# Software-Automation-Holdings-LLC.
land-pr() {
	emulate -L zsh
	local org="" name="" pr="" spec="" repo dest title gh_bin=gh pr_json pr_state pr_url run_id
	local model="claude-sonnet-5" # Model for autopilot executor
	local max_continues="200"     # Max autopilot continues for unattended landing
	(($+commands[ghx])) && gh_bin=ghx
	while (($#)); do
		case $1 in
		--org)
			[[ -n ${2-} ]] || {
				__ -t failed "land-pr: --org needs a value"
				return 1
			}
			org=$2
			shift 2
			;;
		--repo)
			[[ -n ${2-} ]] || {
				__ -t failed "land-pr: --repo needs a value"
				return 1
			}
			name=$2
			shift 2
			;;
		--pr)
			[[ -n ${2-} ]] || {
				__ -t failed "land-pr: --pr needs a value"
				return 1
			}
			pr=$2
			shift 2
			;;
		--)
			shift
			break
			;;
		-*)
			__ -t failed $'usage: land-pr --org ORG --repo REPO --pr N\n       land-pr owner/repo#N'
			return 1
			;;
		*)
			if [[ -n $spec ]]; then
				__ -t failed $'usage: land-pr --org ORG --repo REPO --pr N\n       land-pr owner/repo#N'
				return 1
			fi
			spec=$1
			shift
			;;
		esac
	done
	if [[ -n $spec ]]; then
		if [[ -n $org || -n $name || -n $pr ]]; then
			__ -t failed "land-pr: pass owner/repo#N or the flags, not both"
			return 1
		fi
		if [[ $spec != */*#<-> ]]; then
			__ -t failed "usage: land-pr owner/repo#N"
			return 1
		fi
		repo=${spec%%#*}
		pr=${spec##*#}
		org=${repo%%/*}
		name=${repo##*/}
	elif [[ -z $org || -z $name || $pr != <-> ]]; then
		__ -t failed $'usage: land-pr --org ORG --repo REPO --pr N\n       land-pr owner/repo#N'
		return 1
	fi
	if [[ $org == Software-Automation-Holdings ]]; then
		org=Software-Automation-Holdings-LLC
	fi
	repo="${org}/${name}"
	run_id=${(L)$(uuidgen)}
	run_id=${run_id[1,8]}
	dest="/tmp/land-pr/${org}-${name}-${pr}-${run_id}"
	title="land-${name}-${pr}-${run_id}"

	pr_json=$(command "$gh_bin" pr view "$pr" --repo "$repo" --json state,url) || return 1
	pr_state=$(print -r -- "$pr_json" | command jq -r .state)
	pr_url=$(print -r -- "$pr_json" | command jq -r .url)
	case $pr_state in
	OPEN) ;;
	MERGED)
		__ "land-pr: ${repo}#${pr} already MERGED ${pr_url}"
		return 0
		;;
	*)
		__ -t failed "land-pr: ${repo}#${pr} is ${pr_state}; only OPEN PRs can land"$'\n'"$pr_url"
		return 1
		;;
	esac

	command mkdir -p -- /tmp/land-pr || return 1
	if [[ ! -d $dest/.git ]]; then
		command "$gh_bin" repo clone "$repo" "$dest" || return 1
	fi
	# Use gh pr checkout to set up the branch with proper upstream tracking.
	# Falls back to plain gh if ghx doesn't support pr checkout.
	(cd "$dest" && command "$gh_bin" pr checkout "$pr" --repo "$repo") || {
		(cd "$dest" && command gh pr checkout "$pr" --repo "$repo") || return 1
	}
	# Verify the branch has an upstream set (for /pr to recognize the PR).
	local upstream
	upstream=$(command git -C "$dest" rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null) || {
		__ -t failed "land-pr: failed to set upstream tracking for PR branch"
		return 1
	}
	if [[ -z "$upstream" || "$upstream" == "@{u}" ]]; then
		__ -t failed "land-pr: PR branch has no upstream; /pr automerge cannot recognize the PR"
		return 1
	fi
	command mise trust --yes "$dest" || return 1

	# Append per-run dest to trustedFolders to avoid Copilot's "Confirm folder trust" prompt
	local copilot_config="$HOME/.copilot/settings.json"
	if [[ -f "$copilot_config" ]]; then
		local tmp_config
		tmp_config=$(mktemp) || return 1
		if command jq --arg path "$dest" '.trustedFolders += [$path] | .trustedFolders |= unique' "$copilot_config" >"$tmp_config" 2>/dev/null; then
			mv "$tmp_config" "$copilot_config"
		else
			rm -f "$tmp_config"
		fi
	fi

	command aoe add --title "$title" --cmd copilot --yolo --launch \
		--cmd-override "copilot --model $model --yolo --autopilot --max-autopilot-continues $max_continues -i \"/pr automerge\"" \
		"$dest" || return 1
	__ "land-pr: ${repo}#${pr} run ${run_id} in ${dest} (aoe session ${title})"
}
