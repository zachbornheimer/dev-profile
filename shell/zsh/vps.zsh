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

# Keep Mac local-first while making `omp --resume <id>` seamlessly pull any session
# that was created or updated in Neon (e.g. on the VPS or in a SESSIONS_DB_URL shell).
omp() {
	emulate -L zsh
	local db_url_file="$HOME/.config/dev-env/runtime/omp-session-db-url"
	if [[ -z ${SESSIONS_DB_URL:-} && -s $db_url_file ]]; then
		local i sid=""
		for ((i = 1; i <= $#; i++)); do
			case "${@[i]}" in
			--resume | -r)
				((i < $#)) && sid="${@[i+1]#omp:}"
				break
				;;
			--resume=*)
				sid="${${@[i]#--resume=}#omp:}"
				break
				;;
			esac
		done
		if [[ -n $sid && $sid != -* ]]; then
			SESSIONS_DB_URL="$(<$db_url_file)" bun -e '
				import { existsSync, mkdirSync, statSync } from "node:fs";
				import { dirname } from "node:path";
				const sid = process.argv[1];
				const sql = new Bun.SQL(process.env.SESSIONS_DB_URL);
				const rows = await sql`SELECT path, content, mtime_ms FROM omp_session_files WHERE path LIKE ${"%" + sid + "%"}`;
				for (const r of rows) {
					if (!r.path.startsWith("/Users/zbornheimer/")) continue;
					const diskMtime = existsSync(r.path) ? Math.trunc(statSync(r.path).mtimeMs) : -1;
					if (diskMtime < Number(r.mtime_ms)) {
						mkdirSync(dirname(r.path), { recursive: true });
						await Bun.write(r.path, r.content);
					}
				}
				await sql.close();
			' "$sid" >/dev/null 2>&1 || true
		fi
	fi
	command omp "$@"
}
