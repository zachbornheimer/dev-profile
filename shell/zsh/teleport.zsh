# teleport — route through home via Tailscale (exit node: zacharys-mini)
# `teleport on`  routes all traffic through the home mini AND reaches the home
#                LAN (192.168.1.0/24) from anywhere — nothing exposed, no DDNS.
# `teleport off` stops routing through home (direct internet); the tailnet
#                stays up, so home services remain reachable by name/IP.
# `teleport status`. Requires the Tailscale app installed + signed in here.
teleport() {
	emulate -L zsh
	local ts node=zacharys-mini
	ts=$(command -v tailscale) ||
		ts=/Applications/Tailscale.app/Contents/MacOS/Tailscale
	[[ -x $ts ]] || {
		__ -t failed "teleport: Tailscale not installed (App Store: Tailscale)"
		return 1
	}
	case "$1" in
	on) "$ts" set --exit-node="$node" --exit-node-allow-lan-access &&
		__ -t success "teleport on — routing through $node" ;;
	off) "$ts" set --exit-node= && __ -t success "teleport off" ;;
	status) "$ts" status ;;
	*)
		__ -t failed "usage: teleport {on|off|status}"
		return 2
		;;
	esac
}
