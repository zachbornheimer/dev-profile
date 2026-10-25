# node.zsh — Dropbox-aware npm/pnpm wrappers.

_dropbox_ignore() {
	if [[ -d ./node_modules ]]; then
		xattr -w com.dropbox.ignored 1 ./node_modules 2>/dev/null || true
		__ "Dropbox: ignored node_modules"
	fi
}

# Both wrappers preserve the real command's exit code — the trailing case statement
# otherwise replaces it with 0, silently turning failed builds/tests green.
npm() {
	command npm "$@"
	local rc=$?
	case "$1" in
	install | i | ci) (($+functions[_dropbox_ignore])) && _dropbox_ignore ;;
	esac
	return $rc
}

pnpm() {
	command pnpm "$@"
	local rc=$?
	case "$1" in
	install | i) (($+functions[_dropbox_ignore])) && _dropbox_ignore ;;
	esac
	return $rc
}
