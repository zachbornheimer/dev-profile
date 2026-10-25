# --- Grok MCP helpers -------------------------------------------------------
# grok --safe-mode [...]  → this process only, no MCP, config.toml untouched
# grok-mcp-on             → persist-enable every configured server
# grok-mcp-off            → persist-disable every configured server
# plain `grok`            → whatever is currently enabled in config.toml

grok::mcp-names() {
	local json out
	out="$(command grok mcp list --json 2>/dev/null)" || out=""
	if [[ -n "$out" ]]; then
		print -r -- "$out" | python3 -c '
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    raise SystemExit(0)
data = json.loads(raw)
items = data
if isinstance(data, dict):
    for key in ("servers", "mcp_servers", "items", "data"):
        if isinstance(data.get(key), list):
            items = data[key]
            break
    else:
        items = [data]
names = []
for item in items:
    if isinstance(item, str):
        names.append(item)
    elif isinstance(item, dict):
        name = item.get("name") or item.get("id") or item.get("server")
        if name:
            names.append(str(name))
for name in names:
    print(name)
' 2>/dev/null
		return 0
	fi
	command grok mcp list 2>/dev/null |
		awk '/^[[:space:]]*[^#[:space:]]/ { gsub(/\r/,""); print $1 }' |
		sed -E 's/\(.*\)//; s/:$//; s/[[:space:]]+$//'
}

grok::safe-env() {
	local -a names=()
	local n
	while IFS= read -r n; do
		[[ -n "$n" ]] && names+="$n"
	done < <(grok::mcp-names)
	local json='{"disabled_mcp_servers":['
	local first=1
	for n in "${names[@]}"; do
		((first)) || json+=','
		first=0
		json+="\"$n\""
	done
	json+=']}'
	export GROK_CONFIG="$json"
	export GROK_CLAUDE_MCPS_ENABLED=0
	export GROK_CURSOR_MCPS_ENABLED=0
	export GROK_MANAGED_MCPS_ENABLED=0
}

__grok() {
	if [[ "$1" == "--safe-mode" ]]; then
		shift
		grok::safe-env
		ai-keys::exec grok "$@"
		return $?
	fi
	if [[ "$1" == "import" ]]; then
		shift
		"${HOME}/.grok/bin/grok-import" "$@"
		return $?
	fi
	ai-keys::exec grok "$@"
}

grok-mcp-off() {
	local n
	while IFS= read -r n; do
		[[ -n "$n" ]] || continue
		command grok mcp disable "$n" && __ -t success "disabled $n" >&2
	done < <(grok::mcp-names)
}

grok-mcp-on() {
	local n
	# include currently disabled rows too
	while IFS= read -r n; do
		[[ -n "$n" ]] || continue
		command grok mcp enable "$n" && __ -t success "enabled $n" >&2
	done < <(grok::mcp-names)
}

alias grok="hermes --yolo --provider xai-oauth --model grok-4.7" # has hooks grok build doesn't.
