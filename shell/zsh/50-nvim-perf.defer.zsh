# Wall-clock wrapper around nvim. Appends one JSONL line per invocation.
# Loaded deferred, after the e/n/vi/vim aliases in aliases.zsh exist.

nvim() {
	emulate -L zsh
	zmodload zsh/datetime 2>/dev/null || true

	local start end ms rc log_path cwd esc ts
	start=$EPOCHREALTIME
	command nvim "$@"
	rc=$?
	end=$EPOCHREALTIME
	printf -v ms '%.3f' $(((end - start) * 1000.0))

	log_path="${NVIM_PERF_LOG:-${XDG_STATE_HOME:-$HOME/.local/state}/nvim/perf.jsonl}"
	cwd=$PWD
	esc=${cwd//\\/\\\\}
	esc=${esc//\"/\\\"}
	esc=${esc//$'\n'/\\n}
	esc=${esc//$'\r'/\\r}
	esc=${esc//$'\t'/\\t}
	ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date +%Y-%m-%dT%H:%M:%SZ)

	mkdir -p "${log_path:h}" 2>/dev/null || true
	printf '{"ts":"%s","event":"wall","ms":%s,"cwd":"%s","rc":%s}\n' \
		"$ts" "$ms" "$esc" "$rc" >>"$log_path" 2>/dev/null || true

	return $rc
}
