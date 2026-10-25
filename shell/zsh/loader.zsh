# loader.zsh — sources every module in ~/.config/zsh, in filename order.
#
#   NN-name.zsh        eager; the number fixes order where it matters
#   name.zsh           eager; order-independent definitions
#   NN-name.defer.zsh  deferred; loaded once by zle-line-init (prompt.zsh), after
#                      the first prompt paints. Only work that forks, sources a
#                      plugin, or needs ZLE belongs here — definitions cost ~2ms.
#   ~/.zshrc.local     machine-local overrides, sourced last
#
# Modules are always sourced from inside a function (this loader, `source`, or
# the zle-line-init widget), so they must declare globals with `typeset -g` and
# must not call `emulate -L` at top level.

typeset -g ZSH_CONFIG_DIR="${ZSH_CONFIG_DIR:-$HOME/.config/zsh}"

# `source` with no file reloads ~/.zshrc; typed at the prompt, it also prints
# each file it loads, nested sources included.
source() {
	local _source_file="${1:-$HOME/.zshrc}"
	local -i _source_verbose=${_source_verbose:-0}
	[[ $ZSH_EVAL_CONTEXT == toplevel:shfunc ]] && _source_verbose=1

	builtin source "$_source_file" "${@:2}" || return $?

	if ((_source_verbose)); then
		__ -t success "Loaded $_source_file"
	fi
}

# Sources one module. With ZSH_BENCH_TRACE set to a file path (zsh-bench does
# this), also appends "phase<TAB>path<TAB>start<TAB>end" for the module.
_zsh_source_module() {
	if [[ -z $ZSH_BENCH_TRACE ]]; then
		source "$2"
		return
	fi
	zmodload zsh/datetime
	local start=$EPOCHREALTIME status_code
	source "$2"
	status_code=$?
	printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$start" "$EPOCHREALTIME" >>"$ZSH_BENCH_TRACE"
	return $status_code
}

_zsh_load_modules() {
	local module
	for module in "$ZSH_CONFIG_DIR"/*.zsh(N); do
		[[ ${module:t} == loader.zsh || $module == *.defer.zsh ]] && continue
		_zsh_source_module eager "$module"
	done
	[[ -f $HOME/.zshrc.local ]] && _zsh_source_module local "$HOME/.zshrc.local"
}

# Called from zle-line-init on every new line; does its work once per load.
_zsh_deferred_init() {
	((${+_ZSH_DEFERRED_DONE})) && return 0
	typeset -g _ZSH_DEFERRED_DONE=1
	[[ -o interactive ]] || return 0
	local module
	for module in "$ZSH_CONFIG_DIR"/*.defer.zsh(N); do
		_zsh_source_module deferred "$module"
	done
}

_zsh_load_modules
# A reload re-arms the deferred modules for the next prompt.
unset _ZSH_DEFERRED_DONE
