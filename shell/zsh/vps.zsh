# vps.zsh — one front door to the on-demand compute arm (backend.ai.lan.zachandaj.com).
#
# The mise tasks live in ~/Developer/Personal/dev-env. `mise -C` changes directory before the
# task runs, so the task cannot see where you typed the command; this wrapper passes "$PWD" as
# --cwd. Run it from the project you want on the box. See dev-env/README.md "Remote Compute Arm".
#
#   vps new [prompt]          new omp session on the box, in this project
#   vps continue [omp:<id>]   move a session (default: this project's latest) to the box
#   vps takeback [omp:<id>]   bring it back here; the box stays up while other sessions run
#   vps run <cmd...>          one-off command on the box, newer files synced back
#   vps run -p "<prompt>"     one-shot omp prompt on the box
#   vps sh                    login shell on the box, in this project
#   vps up | down | status    lifecycle (down evacuates dirty repos first)
vps() {
	emulate -L zsh
	local env_dir="$HOME/Developer/Personal/dev-env"
	local verb="${1:-status}"
	(($#)) && shift
	case "$verb" in
	new | continue | takeback | run)
		mise -C "$env_dir" run "vps:$verb" --cwd "$PWD" "$@"
		;;
	sh)
		mise -C "$env_dir" run vps:run --cwd "$PWD"
		;;
	up | down | status)
		mise -C "$env_dir" run "vps:$verb" "$@"
		;;
	*)
		print -u2 "usage: vps {new|continue|takeback|run|sh|up|down|status} [args]"
		return 2
		;;
	esac
}
