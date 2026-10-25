# prompt-demo.zsh — p_demo: renders every prompt variant from simulated state (see 30-prompt.zsh).

# ---- demo: render every variant from simulated state (no real git needed) ---
p_demo() {
	local saved_git=$_p_git saved_root=$_p_repo_root saved_exit=$_p_exit saved_dur=$_p_dur saved_fp=$_p_fakepath saved_aws=$_p_aws_seen
	local r1="~/Dropbox/Zysys/Software/obsidian-backup" r2="~/Zysys/Software/contactctl"
	_demo() { # label fakepath reporoot exit dur | branch dirty ahead behind stash action
		local label=$1 fp=$2 root=$3 ex=$4 dur=$5
		shift 5
		_p_fakepath=$fp
		_p_repo_root=$root
		_p_exit=$ex
		_p_dur=$dur
		_p_git=$(prompt::git-segment "$@")
		prompt::build
		print -P -- "%B$label%b"
		print -P -- "$PROMPT${RPROMPT:+   right→ $RPROMPT}"
		print
	}
	print -P -- "%B── simulated prompt variants ──────────────────────────────%b"
	print
	_demo "clean repo (root)" "$r1" "$r1" 0 0 main "" 0 0 0 ""
	_demo "dirty + ahead, subdir" "$r1/internal/sync" "$r1" 0 0 main "*" 2 0 0 ""
	_demo "behind + 2 stashes" "$r2" "$r2" 0 0 main "" 0 3 2 ""
	_demo "failed build (exit 1)" "$r1" "$r1" 1 0 main "*" 0 0 0 ""
	_demo "long command (8.2s)" "$r1/internal/pack" "$r1" 0 8.2 main "" 1 0 0 ""
	_demo "mid-rebase, conflict" "$r2" "$r2" 0 0 main "*" 0 0 0 "rebase 2/5"
	_demo "not a repo" "~/Downloads/photos" "" 0 0 "" "" 0 0 0 ""
	# AWS guardrail (shown after an aws command; prod shouts red).
	_p_fakepath="~/Zysys/infra"
	_p_repo_root="~/Zysys/infra"
	_p_exit=0
	_p_dur=0
	_p_aws_seen=1
	_p_git=$(prompt::git-segment main "" 0 0 0 "")
	AWS_PROFILE=prod prompt::build
	print -P -- "%BAWS prod (after an aws command)%b"
	print -P -- "$PROMPT"
	print
	print -P -- "%B── transient: what each past command collapses to ─────────%b"
	print -P -- "${_p_c[dim]}14:23${_p_c[rst]} ${_p_c[dim]}❯${_p_c[rst]} make build"
	print
	unfunction _demo
	_p_git=$saved_git _p_repo_root=$saved_root _p_exit=$saved_exit _p_dur=$saved_dur _p_fakepath=$saved_fp _p_aws_seen=$saved_aws
}
