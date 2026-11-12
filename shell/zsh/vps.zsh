# vps.zsh — front door to the on-demand compute arm (backend.ai.lan.zachandaj.com).
#
#   ompr                      start a new omp session on the remote box (in this repo)
#   ompr "prompt..."          start a new remote omp session with an initial prompt
#   ompr -c | --continue      move this repo's latest session to the remote box
#   ompr -r <id> | <id>       move session <id> (or omp:<id>) to the remote box
#   ompr -p "prompt..."       run a one-shot headless prompt on the remote box
#
#   omp -r <id> | -c          if the session's latest entry in Neon was written on the
#                             remote Linux compute arm, automatically takes it over on the
#                             Mac: syncs newer repo files back, stops the remote omp for
#                             that session, scales down the box in the background if idle,
#                             and resumes directly against Neon.
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
	local sid=""
	local i

	for ((i = 1; i <= $#raw_args; i++)); do
		case "${raw_args[i]}" in
		--resume | -r)
			final_args+=("${raw_args[i]}")
			if ((i < $#raw_args)) && [[ "${raw_args[i+1]}" != -* ]]; then
				sid="${raw_args[i+1]#omp:}"
				final_args+=("$sid")
				((i++))
			fi
			;;
		--resume=*)
			sid="${${raw_args[i]#--resume=}#omp:}"
			final_args+=("--resume=$sid")
			;;
		--continue | -c)
			final_args+=("${raw_args[i]}")
			;;
		omp:*)
			sid="${raw_args[i]#omp:}"
			final_args+=("--resume" "$sid")
			;;
		*)
			if [[ -z $sid && ${raw_args[i]} =~ '^[0-9a-f]{8}-[0-9a-f]{4}-' ]]; then
				sid="${raw_args[i]}"
				final_args+=("--resume" "$sid")
			else
				final_args+=("${raw_args[i]}")
			fi
			;;
		esac
	done

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

# Probe an ssh host; if Tailscale SSH demands a browser re-auth, open the check page and wait
# (up to 90s) for approval instead of hanging silently. Returns ssh's success.
_omp_probe_remote() {
	emulate -L zsh
	setopt local_options no_monitor no_notify
	local host="$1" out pid url opened=0 n
	out="$(mktemp -t omp-probe.XXXXXX)" || return 1
	timeout 90 ssh -o LogLevel=INFO -o BatchMode=yes -o ConnectTimeout=2 "$host" true >"$out" 2>&1 </dev/null &
	pid=$!
	for ((n = 0; n < 180; n++)); do
		kill -0 $pid 2>/dev/null || break
		if ((!opened)); then
			url="$(grep -Eo 'https://login\.tailscale\.com/a/[A-Za-z0-9]+' "$out" 2>/dev/null | head -n1)"
			if [[ -n $url ]]; then
				opened=1
				print -u2 "[omp] Tailscale re-auth needed; opening $url (waiting up to 90s)..."
				open "$url" >/dev/null 2>&1 || true
			fi
		fi
		sleep 0.5
	done
	wait $pid 2>/dev/null
	local rc=$?
	command rm -f "$out"
	return $rc
}

# On the Mac, `omp` reads and writes directly to Neon (`omp_session_files_entries`).
# When resuming or continuing a session whose latest entry was written on the remote
# Linux compute arm, `omp` syncs newer working-tree files from the box, stops any
# remote omp holding that session, and scales down the box in the background if idle.
omp() {
	emulate -L zsh
	local db_url_file="$HOME/.config/dev-env/runtime/omp-session-db-url"
	local -a args=("$@")
	if [[ $OSTYPE == darwin* && (-n ${SESSIONS_DB_URL:-} || -s $db_url_file) ]]; then
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
			local meta db_url="${SESSIONS_DB_URL:-$(<$db_url_file)}"
			meta="$(SESSIONS_DB_URL="$db_url" bun -e '
				const sid = process.argv[1] || "";
				const cwd = process.argv[2] || "";
				const bucket = "-" + cwd.replace(/^\/Users\/[^/]+\/?/, "").replace(/[\/_]/g, "-");
				const sql = new Bun.SQL(process.env.SESSIONS_DB_URL);
				const pattern = sid ? `%${sid}%.jsonl` : `%/${bucket}/%.jsonl`;
				const rows = await sql`
					SELECT f.path,
					       COALESCE(
					         (SELECT string_agg(e.line, ${""} ORDER BY e.seq ASC) FROM omp_session_files_entries e WHERE e.path = f.path AND e.seq <= 2),
					         left(f.content, 2048)
					       ) AS head,
					       COALESCE(
					         (SELECT e.line FROM omp_session_files_entries e WHERE e.path = f.path ORDER BY e.seq DESC LIMIT 1),
					         right(f.content, 4096)
					       ) AS tail_line
					FROM omp_session_files f
					WHERE f.path LIKE ${pattern}
					ORDER BY f.mtime_ms DESC
					LIMIT 1
				`;
				await sql.close();
				const r = rows[0];
				if (r && String(r.tail_line || "").includes("\"platform\":\"linux\"")) {
					const m = String(r.head || "").match(/"cwd":"([^"]+)"/);
					const localDir = m ? m[1].replace(/^\/home\/zbornheimer\b/, "/Users/zbornheimer") : "";
					const idMatch = String(r.path || "").match(/_([0-9a-f-]{36})\.jsonl$/);
					const sessionId = sid || (idMatch ? idMatch[1] : "");
					console.log(JSON.stringify({ tookOver: true, sessionId, localDir }));
				}
						' "$sid" "$PWD" 2>/dev/null)" || meta=""
			if [[ -n $meta ]]; then
				local tk_sid tk_dir remote_dir
				tk_sid="$(jq -r '.sessionId // empty' <<<"$meta" 2>/dev/null)"
				tk_dir="$(jq -r '.localDir // empty' <<<"$meta" 2>/dev/null)"
				[[ -z $tk_dir ]] && tk_dir="$PWD"
				case "$tk_dir" in
				/Users/zbornheimer | /Users/zbornheimer/*)
					remote_dir="/home/zbornheimer${tk_dir#/Users/zbornheimer}"
					;;
				*)
					remote_dir="$tk_dir"
					;;
				esac
				print -u2 "[omp] taking over session ${tk_sid:-latest} from remote compute arm..."
				local -a rssh=(timeout 6 ssh -o BatchMode=yes -o ConnectTimeout=2)
				if _omp_probe_remote backend.ai.lan.zachandaj.com; then
					if [[ -n $tk_sid ]]; then
						"${rssh[@]}" backend.ai.lan.zachandaj.com "pkill -u zbornheimer -f 'omp.*${tk_sid}' 2>/dev/null || true" >/dev/null 2>&1 || true
					fi
					if [[ -d $tk_dir && -n $remote_dir ]]; then
						timeout 120 rsync -azu -e "ssh -o BatchMode=yes -o ConnectTimeout=2" --exclude='.worktrees' --exclude='node_modules' --exclude='.venv' --exclude='target' --exclude='__pycache__' \
							"backend.ai.lan.zachandaj.com:${remote_dir}/" "${tk_dir}/" >/dev/null 2>&1 || true
					fi
					if [[ "$("${rssh[@]}" backend.ai.lan.zachandaj.com "if pgrep -u zbornheimer -f '(^|/)(omp|atask)([[:space:]]|$)' >/dev/null || [ \"\$(who | grep -c 'pts/')\" -gt 0 ]; then echo busy; else echo idle; fi" 2>/dev/null)" == idle ]]; then
						print -u2 "[omp] no other active sessions on remote box; scaling down in background..."
						(nohup mise -C "$HOME/Developer/Personal/dev-env" run vps:down >/dev/null 2>&1 </dev/null &)
					fi
				fi
			fi
		fi
	fi
	command omp "${args[@]}"
}
