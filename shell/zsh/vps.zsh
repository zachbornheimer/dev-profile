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
	if [[ -f "$env_dir/mise.toml" ]] && ! grep -q "exclude='backups'" "$env_dir/mise.toml" 2>/dev/null; then
		perl -pi -e "s/--exclude='\\.worktrees'/--exclude='.worktrees' --exclude='backups' --filter=':- .gitignore'/g" "$env_dir/mise.toml" 2>/dev/null || true
	fi
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
	local -a final_args=() pass_args=()
	local sid="" mode=""
	local i

	# final_args: the full omp command line (for vps run).
	# pass_args: everything except the session selector (for vps continue).
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
				pass_args+=("${raw_args[i]}")
			fi
			;;
		esac
	done

	# If a session ID was passed, sync its session file to Neon so the remote box has it
	if [[ -n $sid || $mode == "continue" ]]; then
		local db_url_file="$HOME/.config/dev-env/runtime/omp-session-db-url"
		local bun_bin="$HOME/.bun/bin/bun"
		[[ -x $bun_bin ]] || bun_bin="bun"
		if [[ -s $db_url_file ]]; then
			SESSIONS_DB_URL="$(<$db_url_file)" "$bun_bin" -e '
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

	# Moving an existing session must go through vps:continue: it resolves the session
	# file from Neon, syncs every repo the session touched, and resumes by remote path
	# from the session's own cwd. A bare `omp --resume <id>` via vps:run searches only
	# the box's disk, where a Mac-born session does not exist ("Session ... not found").
	local rc=0
	if [[ -n $sid ]]; then
		vps continue "$sid" "${pass_args[@]}"
		rc=$?
	elif [[ $mode == "continue" ]]; then
		vps continue "" "${pass_args[@]}"
		rc=$?
	elif ((${#final_args[@]} == 0)); then
		# Pass the command as separate words: vps:run re-quotes each word for the remote shell.
		vps run "exec" "omp"
		rc=$?
	else
		vps run "exec" "omp" "${final_args[@]}"
		rc=$?
	fi
	# /switch-to-local on the box (omp extension switch-session) exits 75 and leaves a marker
	# naming the session; resume it here, which takes it back from Neon and the box.
	((rc == 75)) && {
		_ompr_return_to_mac
		return $?
	}
	return $rc
}

# Resume the session the box's omp handed back with /switch-to-local: read and remove the
# marker it wrote, then `omp --resume <id> "."` (the omp function below takes the session over).
_ompr_return_to_mac() {
	emulate -L zsh
	local meta sid
	meta="$(timeout 10 ssh -o BatchMode=yes -o ConnectTimeout=5 backend.ai.lan.zachandaj.com 'f="$HOME/.omp/agent/switch-to-local.json"; cat "$f" && rm -f "$f"' 2>/dev/null)" || meta=""
	sid="$(jq -r '.sessionId // empty' <<<"$meta" 2>/dev/null)"
	if [[ -z $sid ]]; then
		print -u2 "[ompr] the box asked to switch to the Mac but left no session marker; resume with: omp --resume <id> ."
		return 75
	fi
	OMP_FORCE_REMOTE_TAKEOVER=1 omp --resume "$sid" "."
}

# Probe an ssh host; if Tailscale SSH demands a browser re-auth, open the check page and wait
# (up to ${OMP_PROBE_TIMEOUT:-30}s) for approval instead of hanging silently. If no Tailscale
# check URL appears within ${OMP_PROBE_NO_URL_TIMEOUT:-5}s, abort immediately.
_omp_probe_remote() {
	emulate -L zsh
	setopt local_options no_monitor no_notify
	local host="$1" out pid url opened=0 n
	local -i max_wait="${OMP_PROBE_TIMEOUT:-30}"
	local -i no_url_wait="${OMP_PROBE_NO_URL_TIMEOUT:-5}"
	local -i ticks=$((max_wait * 4))
	local -i no_url_ticks=$((no_url_wait * 4))
	out="$(mktemp -t omp-probe.XXXXXX)" || return 1
	timeout "$max_wait" ssh -o LogLevel=INFO -o BatchMode=yes -o ConnectTimeout=2 "$host" true >"$out" 2>&1 </dev/null &
	pid=$!
	for ((n = 0; n < ticks; n++)); do
		kill -0 $pid 2>/dev/null || break
		if ((!opened)); then
			url="$(grep -Eo 'https://login\.tailscale\.com/a/[A-Za-z0-9]+' "$out" 2>/dev/null | head -n1)"
			if [[ -n $url ]]; then
				opened=1
				print -u2 "[omp] Tailscale re-auth needed; opening $url (waiting up to ${max_wait}s)..."
				"${OMP_OPEN_CMD:-open}" "$url" >/dev/null 2>&1 || true
			elif ((n >= no_url_ticks)); then
				kill $pid 2>/dev/null || true
				break
			fi
		fi
		sleep 0.25
	done
	kill -0 $pid 2>/dev/null && kill $pid 2>/dev/null || true
	wait $pid 2>/dev/null
	local rc=$?
	command rm -f "$out"
	return $rc
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
	# The takeback must run whenever the shared store is readable — including when
	# SESSIONS_DB_URL is already exported (mise exports it at shell start). `omp
	# --resume <id>` lists sessions from local *.jsonl files only: its CLI never
	# opens the SQL store, so a session living only in Neon is invisible by id and
	# this pull is the only fallback. Gating on `-z ${SESSIONS_DB_URL:-}` disabled
	# exactly that case and produced "Session ... not found".
	if [[ $OSTYPE == darwin* && -s $db_url_file ]]; then
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
			local meta bun_bin="$HOME/.bun/bin/bun"
			[[ -x $bun_bin ]] || bun_bin="bun"
			meta="$(SESSIONS_DB_URL="$(<$db_url_file)" "$bun_bin" -e '
				import { existsSync, mkdirSync, statSync } from "node:fs";
				import { dirname } from "node:path";
				const sid = process.argv[1] || "";
				const cwd = process.argv[2] || "";
				const home = (process.env.HOME || "").replace(/\/+$/, "");
				const toLocal = (p) => String(p || "").replace(/^\/(?:home|Users)\/z(?:ach)?bornheimer(?=\/|$)/, home);
				const bucket = "-" + cwd.replace(/^\/Users\/[^/]+\/?/, "").replace(/[\/_]/g, "-");
				const sql = new Bun.SQL(process.env.SESSIONS_DB_URL);
				let rows = [];
				// Metadata first: the common resume is a session that never left this Mac, and it must cost one
				// small query, not a download of every matching transcript (subagents included).
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
					let mainContent = "";
					for (const s of stale) {
						const [r] = await sql`SELECT path, content FROM omp_session_files WHERE path = ${s.path}`;
						if (!r) continue;
						const lp = toLocal(r.path);
						mkdirSync(dirname(lp), { recursive: true });
						await Bun.write(lp, r.content);
						if (r.path.endsWith(".jsonl")) mainContent = String(r.content || "");
					}
					const main = rows.find((r) => r.path.endsWith(".jsonl"));
					if (main) {
						if (!mainContent) {
							const [h] = await sql`SELECT content FROM omp_session_files WHERE path = ${main.path}`;
							mainContent = String(h?.content || "");
						}
						const head = mainContent.slice(0, 2048);
						const m = head.match(/"cwd":"([^"]+)"/);
						if (m) localDir = toLocal(m[1]);
						const idMatch = main.path.match(/_([0-9a-f-]{36})\.jsonl$/);
						if (!sessionId && idMatch) sessionId = idMatch[1];
						// Only trigger remote compute-arm SSH takeover when the session in Neon
						// actually ran on the Linux compute arm (/home/...) or /switch-to-local asked for it.
						// When SESSIONS_DB_URL is exported on the Mac, Mac-local turns write to Neon
						// without touching local disk; materializing the file above is enough for those.
						const cwds = [...mainContent.matchAll(/current working directory: \x27([^\x27]+)\x27/g)].map((x) => x[1]);
						const lastCwd = cwds.length ? cwds[cwds.length - 1] : (m ? m[1] : "");
						if (
							process.env.OMP_FORCE_REMOTE_TAKEOVER === "1" ||
							main.path.startsWith("/home/") || // portable-home-ok: detects a session written on the Linux compute arm
							lastCwd.startsWith("/home/") // portable-home-ok: same detection
						) {
							tookOver = true;
						}
					}
				}
				await sql.close();
				if (tookOver) {
					console.log(`${sessionId}\t${localDir}`);
				}
						' "$sid" "$PWD" 2>/dev/null)" || meta=""
			if [[ -n $meta ]]; then
				local tk_sid="${meta%%$'\t'*}"
				local tk_dir="${meta#*$'\t'}"
				[[ -z $tk_dir ]] && tk_dir="$PWD"
				case "$tk_dir" in
				"$HOME" | "$HOME"/*)
					remote_dir="/home/zbornheimer${tk_dir#"$HOME"}" # portable-home-ok: the compute arm's home, not this machine's
					;;
				*)
					remote_dir="$tk_dir"
					;;
				esac
				print -u2 "[omp] taking over session ${tk_sid:-latest} from remote compute arm..."
				# Tailscale SSH can block on a browser "check" re-auth that ConnectTimeout does not
				# cover. The probe opens that check page for you and waits for approval (bounded);
				# every later remote call is hard-bounded too, so a failed probe skips takeover.
				local -a rssh=(timeout 6 ssh -o BatchMode=yes -o ConnectTimeout=2)
				if _omp_probe_remote backend.ai.lan.zachandaj.com; then
					if [[ -n $tk_sid ]]; then
						"${rssh[@]}" backend.ai.lan.zachandaj.com "pkill -u zbornheimer -f 'omp.*${tk_sid}' 2>/dev/null || true" >/dev/null 2>&1 || true
					fi
					if [[ -d $tk_dir && -n $remote_dir ]] && source "$HOME/Developer/Personal/dev-env/tools/vps/sync-scope.sh" && vps_syncable "$tk_dir"; then
						timeout 120 rsync -azu -e "ssh -o BatchMode=yes -o ConnectTimeout=2" --exclude='.worktrees' --exclude='backups' --filter=':- .gitignore' --exclude='node_modules' --exclude='.venv' --exclude='target' --exclude='__pycache__' \
							"backend.ai.lan.zachandaj.com:${remote_dir}/" "${tk_dir}/" >/dev/null 2>&1 || true
					fi
					# Scale down only on an explicit "idle" answer, never on a timeout or ssh failure.
					if [[ "$("${rssh[@]}" backend.ai.lan.zachandaj.com "if pgrep -u zbornheimer -f '(^|/)(omp|atask)([[:space:]]|$)' >/dev/null || [ \"\$(who | grep -c 'pts/')\" -gt 0 ]; then echo busy; else echo idle; fi" 2>/dev/null)" == idle ]]; then
						print -u2 "[omp] no other active sessions on remote box; scaling down in background..."
						(nohup mise -C "$HOME/Developer/Personal/dev-env" run vps:down >/dev/null 2>&1 </dev/null &)
					fi
				fi
			fi
		fi
	fi
	_omp_run_parkable "${args[@]}"
}

# Interactive scale-to-zero. The terminal-park omp extension exits an idle omp after a long idle and leaves
# the session id in $OMP_TERMINAL_PARK_MARKER. This shell is already the terminal's holder, so it stays (a few
# MB instead of ~500 MB of omp) and runs `omp --resume <id>` on the next keypress. That keypress is consumed.
# Opt out with OMP_TERMINAL_PARK_OFF=1. Not used when stdin/stdout is not a terminal.
# Sourced by vps.zsh; kept standalone for FIFO-driven tests.
_omp_park_wait() {
	emulate -L zsh
	zmodload zsh/zselect || return 1
	local sid=$1 key=$2 input=${3:-0} fd byte dir cmd
	local -a ready
	if [[ -z $key ]]; then
		print -u2 "[omp] parked session $sid to free memory. Press any key to resume (Ctrl+C to stay out)."
		read -r -k1 -u $input byte || return 1
		[[ $byte != $'\x03' ]]
		[[ $byte != $'\x03' ]] || return 1
		# Startup takes up to a minute on a loaded machine; say so before the screen goes quiet.
		print -u2 "\n[omp] resuming session $sid ... (can take up to a minute under load)"
		return 0
	fi
	[[ -p $dir/wake.fifo ]] || return 1
	cmd=$(<$dir/cmd)
	print -u2 "[omp] tool running: ${cmd[1,60]} | Ctrl+C interrupts it | any other key attaches"
	exec {fd}<>"$dir/wake.fifo" || return 1
	# Check after opening: completion before open need not leave a FIFO byte behind.
	if [[ ! -f $dir/done.json ]]; then
		zselect -r $input $fd -a ready || {
			exec {fd}>&-
			return 1
		}
		if ((${ready[(Ie)$input]})); then
			read -r -k1 -u $input byte || {
				exec {fd}>&-
				return 1
			}
			if [[ $byte == $'\x03' ]]; then
				"$OMP_JOBOWNER" kill "$sid" "$key" || {
					exec {fd}>&-
					return 1
				}
			fi
		fi
	fi
	exec {fd}>&-
}

_omp_run_parkable() {
	emulate -L zsh
	local marker rc sid kind key saved
	if [[ ! -t 0 || ! -t 1 || -n ${OMP_TERMINAL_PARK_OFF:-} ]]; then
		command omp "$@"
		return
	fi
	if [[ -z ${OMP_JOBOWNER:-} && -f $HOME/Developer/Personal/dev-env/apps/omp-broker/jobowner.sh ]]; then
		export OMP_JOBOWNER=$HOME/Developer/Personal/dev-env/apps/omp-broker/jobowner.sh
	fi
	marker=$(mktemp "${TMPDIR:-/tmp}/omp-park.XXXXXX") || {
		command omp "$@"
		return
	}
	OMP_TERMINAL_PARK_MARKER=$marker command omp "$@"
	rc=$?
	while [[ -s $marker ]]; do
		{
			IFS= read -r sid
			read -r kind key
		} <"$marker"
		: >"$marker"
		[[ $kind == tool ]] || key=""
		# Raw mode makes Ctrl+C a readable byte instead of killing the holder shell.
		saved=$(stty -g </dev/tty) || break
		stty -icanon -echo -isig min 1 time 0 </dev/tty
		{
			_omp_park_wait "$sid" "$key"
			rc=$?
		} always { stty "$saved" </dev/tty; }
		((rc == 0)) || break
		OMP_TERMINAL_PARK_MARKER=$marker command omp --resume "$sid"
		rc=$?
	done
	rm -f "$marker"
	return $rc
}
