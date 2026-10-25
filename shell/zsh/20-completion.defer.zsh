# 20-completion.defer.zsh — compinit and completion registrations.

autoload -Uz compinit
command mkdir -p "$HOME/.cache/zsh"
fpath=(${fpath:#/usr/local/share/zsh/site-functions})
fpath=(${^fpath}(N-/))
_zcompdump="$HOME/.cache/zsh/.zcompdump"
_zcompdump_warm() {
	emulate -L zsh -o extendedglob
	[[ -s $1 && -z ${1}(#qN.mh+24) ]]
}
if _zcompdump_warm "$_zcompdump"; then
	compinit -C -d "$_zcompdump"
else
	compinit -d "$_zcompdump"
fi
unfunction _zcompdump_warm
if [[ -s $_zcompdump && (! -s ${_zcompdump}.zwc || $_zcompdump -nt ${_zcompdump}.zwc) ]]; then
	zcompile "$_zcompdump" &!
fi
unset _zcompdump

if ((${+functions[_awsp]})); then
	compdef _awsp awsp
fi
if ((${+functions[_opssh_keys]})); then
	compdef _opssh_keys opssh
fi

compctl -K _jina jina
_jina() {
	local words completions
	read -cA words
	if [ "${#words}" -eq 2 ]; then
		completions="$(jina commands)"
	else
		completions="$(jina completions ${words[2,-2]})"
	fi
	reply=(${(ps:\n:)completions})
}
