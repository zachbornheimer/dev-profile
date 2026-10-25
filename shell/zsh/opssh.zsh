# The 1Password agent serves every key at once, so a bare `ssh` can exceed a
# server's MaxAuthTries before offering the right one. These helpers pin a
# single key via its mirrored public key in $OP_SSH_DIR (run `op-ssh-sync` to
# build/refresh the mirror; private keys stay in 1Password).

# opssh <keyname> user@host [ssh args...] — connect offering ONLY that key.
opssh() {
	emulate -L zsh
	local name="$1"
	if [[ -z $name ]]; then
		__ -t failed "usage: opssh <keyname> user@host [ssh args...]"
		[[ -d $OP_SSH_DIR ]] && __ -o stderr "keys: ${(j:, :)$(cd $OP_SSH_DIR && print -l -- *.pub(N:r))}"
		return 2
	fi
	shift
	local pub="$OP_SSH_DIR/$name.pub"
	[[ -r $pub ]] || {
		__ -t failed "opssh: no key '$name' — run op-ssh-sync"
		return 1
	}
	ssh -i "$pub" -o IdentitiesOnly=yes "$@"
}

# opssh-pin <host> <keyname> [user] — make a plain `ssh <host>` use that key.
opssh-pin() {
	emulate -L zsh
	local host="$1" name="$2" user="$3" cfg="$HOME/.ssh/config"
	[[ -n $host && -n $name ]] || {
		__ -t failed "usage: opssh-pin <host> <keyname> [user]"
		return 2
	}
	[[ -r "$OP_SSH_DIR/$name.pub" ]] || {
		__ -t failed "opssh-pin: no key '$name' — run op-ssh-sync"
		return 1
	}
	if grep -qE "^Host[[:space:]]+${host}([[:space:]]|\$)" "$cfg" 2>/dev/null; then
		__ -t failed "opssh-pin: $cfg already has a Host block for '$host' — left untouched"
		return 1
	fi
	{
		print -- ""
		print -- "Host $host"
		[[ -n $user ]] && print -- "  User $user"
		print -- "  IdentityFile $OP_SSH_DIR/$name.pub"
		print -- "  IdentitiesOnly yes"
	} >>"$cfg"
	__ -t success "opssh-pin: pinned '$host' -> '$name' in $cfg"
}

# Tab-complete mirrored key names for `opssh`.
_opssh_keys() {
	[[ -d $OP_SSH_DIR ]] || return
	compadd -- ${(f)"$(cd $OP_SSH_DIR && print -l -- *.pub(N:r))"}
}
