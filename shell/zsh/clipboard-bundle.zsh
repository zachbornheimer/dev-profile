# REPLY is the directory, defaulting to "."; reply is the fd options.
clipboard-bundle::directory-request() {
	emulate -L zsh
	setopt nounset

	local arg
	local -i has_directory=0

	REPLY='.'
	reply=(--type file --print0 --exclude .git)
	for arg in "$@"; do
		case "$arg" in
		--include-hidden)
			reply+=(--hidden)
			;;
		--include-gitignored)
			reply+=(--no-ignore-vcs)
			;;
		-*)
			__ -t failed "cxd: unknown option: $arg"
			return 2
			;;
		*)
			if ((has_directory)); then
				__ -t failed "cxd: expected at most one directory"
				return 2
			fi
			REPLY="$arg"
			has_directory=1
			;;
		esac
	done
}

clipboard-bundle::frame() {
	emulate -L zsh
	setopt nounset

	local label="$1"
	local file="$2"

	print -r -- "<<< FILE: $label >>>"
	print
	cat -- "$file" || return
	print
	print
	print -r -- "<<< END FILE: $label >>>"
	print
}

clipboard-bundle::write-files() {
	emulate -L zsh
	setopt nounset

	local file
	for file in "$@"; do
		clipboard-bundle::frame "${file:A}" "$file" || return
	done
}

clipboard-bundle::write-tree() {
	emulate -L zsh
	setopt nounset pipefail

	local target_dir="$1"
	shift
	local -a fd_opts=("$@")

	# Subshell so cd and a failed read's exit cannot change or kill the caller's shell.
	(
		local file relative_path
		builtin cd -q -- "$target_dir" || exit 1
		fd "${fd_opts[@]}" . . | sort -z | {
			while IFS= read -r -d '' file; do
				relative_path="${file#./}"
				clipboard-bundle::frame "./$relative_path" "$file" || exit 1
			done
		}
	)
}

clipboard-bundle::copy-stream() {
	emulate -L zsh
	setopt nounset pipefail

	local cmd="$1"
	local subject="$2"
	shift 2
	local -a clip_cmd

	clipboard::copy-cmd || {
		__ -t failed "$cmd: no supported clipboard tool found (pbcopy, xclip, xsel)"
		return 1
	}
	clip_cmd=("${reply[@]}")
	"$@" | "${clip_cmd[@]}" || {
		__ -t failed "$cmd: could not copy $subject to clipboard"
		return 1
	}
}

cxf() {
	emulate -L zsh
	setopt nounset

	local target_file
	local -a files

	if (($# == 0)); then
		__ -t failed "usage: cxf <file>..."
		return 2
	fi
	for target_file in "$@"; do
		if [[ ! -f "$target_file" ]]; then
			__ -t failed "cxf: file not found: $target_file"
			return 1
		fi
		files+=("$target_file")
	done

	clipboard-bundle::copy-stream cxf "file contents" clipboard-bundle::write-files "${files[@]}" || return
	if (($# == 1)); then
		__ -t success "Copied $1 to clipboard"
	else
		__ -t success "Copied $# files to clipboard"
	fi
}

cxd() {
	emulate -L zsh
	setopt nounset

	local target_dir
	local -a fd_opts

	clipboard-bundle::directory-request "$@" || return
	target_dir="$REPLY"
	fd_opts=("${reply[@]}")

	if [[ ! -d "$target_dir" ]]; then
		__ -t failed "cxd: directory not found: $target_dir"
		return 1
	fi
	if ((!$+commands[fd])); then
		__ -t failed "cxd: fd is required"
		return 1
	fi

	clipboard-bundle::copy-stream cxd "directory contents" clipboard-bundle::write-tree "$target_dir" "${fd_opts[@]}" || return
	__ -t success "Copied directory tree from $target_dir to clipboard"
}
