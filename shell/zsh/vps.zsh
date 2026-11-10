# vps.zsh — front door to the on-demand compute arm (backend.ai.lan.zachandaj.com).
#
#   ompr                      start a new omp session on the remote box (in this repo)
#   ompr "prompt..."          start a new remote omp session with an initial prompt
#   ompr -c | --continue      move this repo's latest session to the remote box
#   ompr -r <id> | <id>       move session <id> (or omp:<id>) to the remote box
#   ompr -p "prompt..."       run a one-shot headless prompt on the remote box
#
#   omp -r <id> | -c          if the session was on the remote box (Neon newer than disk),
#                             automatically takes it over on the Mac: syncs newer repo files
#                             and Neon turns back, stops the remote omp for that session,
#                             scales down the box in the background if idle, and resumes here.
#
#   vps {new|continue|takeback|run|sh|up|down|status} [args]
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

ompr() {
	emulate -L zsh
	if [[ ${HERDR_ENV:-} == 1 && -n ${HERDR_PANE_ID:-} ]]; then
		herdr pane report-metadata "$HERDR_PANE_ID" \
			--source zsh-fg \
			--agent omp \
			--display-agent "☁️π" &>/dev/null
	fi

	local -a raw_args=("$@")
	local -a final_args=()
	local sid="" mode=""
	local i

	for ((i = 1; i <= $#raw_args; i++)); do
		case "${raw_args[i]}" in
		--resume | -r)
			mode="resume"
			final_args+=("${raw_args[i]}")
			if ((i < $#raw_args)) && [[ "${raw_args[i+1]}" != -* ]]; then
				sid="${raw_args[i+1]#omp:}"
				final_args+=("$sid")
				((i++))
			fi
			;;
		--resume=*)
			mode="resume"
			sid="${${raw_args[i]#--resume=}#omp:}"
			final_args+=("--resume=$sid")
			;;
		--continue | -c)
			mode="continue"
			final_args+=("${raw_args[i]}")
			;;
		omp:*)
			mode="resume"
			sid="${raw_args[i]#omp:}"
			final_args+=("--resume" "$sid")
			;;
		*)
			if [[ -z $sid && ${raw_args[i]} =~ '^[0-9a-f]{8}-[0-9a-f]{4}-' ]]; then
				mode="resume"
				sid="${raw_args[i]}"
				final_args+=("--resume" "$sid")
			else
				final_args+=("${raw_args[i]}")
			fi
			;;
		esac
	done

	# If a session ID was passed, sync its session file to Neon so the remote box has it
	if [[ -n $sid || $mode == "continue" ]]; then
		local db_url_file="$HOME/.config/dev-env/runtime/omp-session-db-url"
		if [[ -s $db_url_file ]]; then
			SESSIONS_DB_URL="$(<$db_url_file)" bun -e '
				import { statSync } from "node:fs";
				import { Glob } from "bun";
				const sid = process.argv[1] || "";
				const sql = new Bun.SQL(process.env.SESSIONS_DB_URL);
				const root = process.env.HOME + "/.omp/agent/sessions";
				const pattern = sid ? `**/*${sid}*.jsonl` : "**/*.jsonl";
				for (const rel of new Glob(pattern).scanSync({ cwd: root, absolute: true })) {
					const st = statSync(rel);
					const mtime = Math.trunc(st.mtimeMs);
					const cur = await sql`SELECT mtime_ms FROM omp_session_files WHERE path = ${rel}`;
					if (!cur.length || Number(cur[0].mtime_ms) < mtime) {
						const content = await Bun.file(rel).text();
						await sql`INSERT INTO omp_session_files (path, content, mtime_ms) VALUES (${rel}, ${content}, ${mtime})
							ON CONFLICT (path) DO UPDATE SET content = EXCLUDED.content, mtime_ms = EXCLUDED.mtime_ms`;
					}
				}
				await sql.close();
			' "$sid" 2>/dev/null || true
		fi
	fi

	local -a quoted_args=()
	for arg in "${final_args[@]}"; do
		quoted_args+=("${(q)arg}")
	done

	if ((${#quoted_args} == 0)); then
		vps run "exec omp"
	else
		vps run "exec omp ${quoted_args[*]}"
	fi
}

# On the Mac, `omp` stays local-first — but if you resume or continue a session whose
# latest turns are in Neon (because it was running on the remote box), `omp` automatically
# takes it over: pulls the Neon transcript to disk, rsyncs newer working-tree files from
# the box, stops any remote omp holding that session, and scales down the box in the
# background if no other session is active on it.
omp() {
	emulate -L zsh
	local db_url_file="$HOME/.config/dev-env/runtime/omp-session-db-url"
	local -a args=("$@")
	if [[ $OSTYPE == darwin* && -z ${SESSIONS_DB_URL:-} && -s $db_url_file ]]; then
		local i sid="" mode=""
		for ((i = 1; i <= $#args; i++)); do
			case "${args[i]}" in
			--resume | -r)
				mode="resume"
				if ((i < $#args)) && [[ "${args[i+1]}" != -* ]]; then
					sid="${args[i+1]#omp:}"
					args[i+1]="$sid"
				fi
				break
				;;
			--resume=*)
				mode="resume"
				sid="${${args[i]#--resume=}#omp:}"
				args[i]="--resume=$sid"
				break
				;;
			--continue | -c)
				mode="continue"
				break
				;;
			omp:*)
				mode="resume"
				sid="${args[i]#omp:}"
				args[i]="--resume"
				args=("${args[1,i]}" "$sid" "${args[i+1,-1]}")
				break
				;;
			esac
		done
		if [[ -n $sid || $mode == "continue" ]]; then
			local meta
			meta="$(SESSIONS_DB_URL="$(<$db_url_file)" bun -e '
				import { existsSync, mkdirSync, statSync } from "node:fs";
				import { dirname } from "node:path";
				const sid = process.argv[1] || "";
				const cwd = process.argv[2] || "";
				const home = (process.env.HOME || "").replace(/\/+$/, "");
				const toLocal = (p) => String(p || "").replace(/^\/(?:home|Users)\/z(?:ach)?bornheimer(?=\/|$)/, home);
				const bucket = "-" + cwd.replace(/^\/Users\/[^/]+\/?/, "").replace(/[\/_]/g, "-");
				const sql = new Bun.SQL(process.env.SESSIONS_DB_URL);
				let rows = [];
				if (sid) {
					rows = await sql`SELECT path, mtime_ms FROM omp_session_files WHERE path LIKE ${"%" + sid + "%"}`;
				} else if (bucket.length > 1) {
					rows = await sql`SELECT path, mtime_ms FROM omp_session_files WHERE path LIKE ${"%/" + bucket + "/%.jsonl"} ORDER BY mtime_ms DESC LIMIT 1`;
				}
				rows = rows
					.map((r) =>({ ...r, localPath: toLocal(r.path) }))
					.filter((r) => home && r.localPath.startsWith(home + "/"));
				const stale = rows.filter((r) =>{
					const diskMtime = existsSync(r.localPath) ? Math.trunc(statSync(r.localPath).mtimeMs) : -1;
					return diskMtime < Number(r.mtime_ms);
				});
				let tookOver = false;
				let sessionId = sid;
				let localDir = "";
				if (stale.length) {
					const paths = stale.map((r) => r.path);
					for (const r of await sql`SELECT path, content FROM omp_session_files WHERE path IN ${sql(paths)}`) {
						const lp = toLocal(r.path);
						mkdirSync(dirname(lp), { recursive: true });
						await Bun.write(lp, r.content);
						tookOver = true;
					}
					const main = rows.find((r) => r.path.endsWith(".jsonl"));
					if (main) {
						const [h] = await sql`SELECT left(content, 2048) AS head FROM omp_session_files WHERE path = ${main.path}`;
						const m = String(h?.head || "").match(/"cwd":"([^"]+)"/);
						if (m) localDir = toLocal(m[1]);
						const idMatch = main.path.match(/_([0-9a-f-]{36})\.jsonl$/);
						if (!sessionId && idMatch) sessionId = idMatch[1];
					}
				}
				await sql.close();
				if (tookOver) {
					console.log(JSON.stringify({ tookOver: true, sessionId, localDir }));
				}
						' "$sid" "$PWD" 2>/dev/null)" || meta=""
			if [[ -n $meta ]]; then
				local tk_sid tk_dir remote_dir
				tk_sid="$(jq -r '.sessionId // empty' <<<"$meta" 2>/dev/null)"
				tk_dir="$(jq -r '.localDir // empty' <<<"$meta" 2>/dev/null)"
				[[ -z $tk_dir ]] && tk_dir="$PWD"
				case "$tk_dir" in
				"$HOME" | "$HOME"/*)
					remote_dir="/home/zbornheimer${tk_dir#"$HOME"}"
					;;
				*)
					remote_dir="$tk_dir"
					;;
				esac
				print -u2 "[omp] taking over session ${tk_sid:-latest} from remote compute arm..."
				if ssh -o ConnectTimeout=2 backend.ai.lan.zachandaj.com true >/dev/null 2>&1; then
					if [[ -n $tk_sid ]]; then
						ssh backend.ai.lan.zachandaj.com "pkill -u zbornheimer -f 'omp.*${tk_sid}' 2>/dev/null || true" >/dev/null 2>&1 || true
					fi
					if [[ -d $tk_dir && -n $remote_dir ]]; then
						rsync -azu --exclude='.worktrees' --exclude='node_modules' --exclude='.venv' --exclude='target' --exclude='__pycache__' \
							"backend.ai.lan.zachandaj.com:${remote_dir}/" "${tk_dir}/" >/dev/null 2>&1 || true
					fi
					if ! ssh backend.ai.lan.zachandaj.com "pgrep -u zbornheimer -f '(^|/)(omp|atask)([[:space:]]|$)' >/dev/null || [ \"\$(who | grep -c 'pts/')\" -gt 0 ]" >/dev/null 2>&1; then
						print -u2 "[omp] no other active sessions on remote box; scaling down in background..."
						(nohup mise -C "$HOME/Developer/Personal/dev-env" run vps:down >/dev/null 2>&1 </dev/null &)
					fi
				fi
			fi
		fi
	fi
	command omp "${args[@]}"
}
