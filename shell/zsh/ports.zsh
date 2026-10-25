# Kill whatever is bound to a port: kp 3000  ==  kill -9 $(lsof -t -i:3000)
kp() {
	emulate -L zsh
	local port="$1"
	if [[ -z "$port" ]]; then
		__ -t failed "Usage: kp <port>"
		return 1
	fi
	local pids
	pids=$(lsof -t -i:"${port}" 2>/dev/null) || true
	if [[ -z "$pids" ]]; then
		__ -t failed "kp: nothing listening on port ${port}"
		return 1
	fi
	kill -9 ${=pids}
}

alias ports='lsof -iTCP -sTCP:LISTEN -n -P | grep LISTEN'
