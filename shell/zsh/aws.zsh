# AWS: creds resolve from the aws-vault keychain via credential_process in
# ~/.aws/config, so `aws --profile X ...` just works (no exec wrapper). `awsp X`
# sets the profile for this shell; `awsp` shows it; `awsp off` clears it.
awsp() {
	emulate -L zsh
	case "$1" in
	"")
		[[ -n $AWS_PROFILE ]] && __ "AWS_PROFILE=$AWS_PROFILE" || __ "no AWS profile set"
		return
		;;
	-u | off)
		unset AWS_PROFILE AWS_DEFAULT_PROFILE
		__ -t success "AWS profile cleared"
		return
		;;
	esac
	export AWS_PROFILE="$1" AWS_DEFAULT_PROFILE="$1"
	__ "AWS_PROFILE=$1"
}
_awsp() { compadd -- ${(f)"$(sed -nE 's/^\[(profile )?([^]]+)\]/\2/p' ~/.aws/config 2>/dev/null)"}; }
