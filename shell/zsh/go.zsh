# go.zsh — `go uninstall`.

go() {
	if [[ "$1" == "uninstall" ]]; then
		shift
		go::uninstall "$@"
		return $?
	fi
	command go "$@"
}

go::human-size() {
	local bytes=$1
	if ((bytes >= 1073741824)); then
		printf '%.1fGB' "$((bytes / 1073741824.0))"
	elif ((bytes >= 1048576)); then
		printf '%.1fMB' "$((bytes / 1048576.0))"
	elif ((bytes >= 1024)); then
		printf '%.1fKB' "$((bytes / 1024.0))"
	else
		printf '%dB' "$bytes"
	fi
}

go::total-bytes() {
	# sum sizes of the given files (BSD stat first, GNU stat fallback)
	local total=0 f sz
	for f in "$@"; do
		sz=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null)
		((total += ${sz:-0}))
	done
	print -r -- "$total"
}

go::uninstall() {
	emulate -L zsh
	setopt no_monitor no_notify
	local arg="$1"

	if [[ -z "$arg" ]]; then
		__ -t failed "go uninstall requires a binary name."
		return 1
	fi

	# Resolve the install dir the same way `go install` does.
	local bindir
	bindir="$(command go env GOBIN 2>/dev/null)"
	[[ -z "$bindir" ]] && bindir="$(command go env GOPATH 2>/dev/null)/bin"
	[[ -z "$bindir" || "$bindir" == "/bin" ]] && bindir="$HOME/go/bin"

	local target="$bindir/$arg"

	# 1. Existence check.
	if [[ ! -e "$target" ]]; then
		__ -t failed "No go binary found with the name \"${arg}\"."
		return 1
	fi

	local abspath="${target:A}" # absolute, symlinks resolved

	# Capture cleanup stats BEFORE deleting (files are gone afterward).
	local -a files_list
	files_list=(${(f)"$(find "$abspath" -type f 2>/dev/null)"})
	local nfiles=${#files_list[@]}
	((nfiles == 0)) && nfiles=1
	local bytes human
	bytes=$(go::total-bytes "${files_list[@]}")
	human=$(go::human-size "$bytes")

	# 2. Delete under the spinner; jq builds the spec so the path needs no escaping.
	local plural=s spec
	((nfiles == 1)) && plural=''
	spec=$(jq -nc --arg path "$abspath" --arg done "($nfiles file$plural, $human)" '{
		type: "pending", message: "Uninstalling \($path)",
		onComplete: {
			success: {type: "success", message: "Uninstalled \($path) ... \($done)"},
			failed: {type: "failed", message: "failed to remove \"\($path)\" (exit %e)."}}}' 2>/dev/null) || spec=
	if [[ -n $spec ]]; then
		__ "$spec" -- rm -rf -- "$abspath"
	else
		__ -t pending "Uninstalling $abspath" -- rm -rf -- "$abspath"
	fi
}
