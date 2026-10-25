# perl.zsh — legacy Perl manager.

# Legacy Perl Manager (perlbrew) - for specific project needs
use-perlbrew() {
	if [[ -f "$HOME/.perlbrew/etc/bashrc" ]]; then
		source "$HOME/.perlbrew/etc/bashrc"
		[[ -n "$1" ]] && perlbrew use "$1"
	else
		__ -t failed "perlbrew not found at ~/.perlbrew/etc/bashrc"
	fi
}
