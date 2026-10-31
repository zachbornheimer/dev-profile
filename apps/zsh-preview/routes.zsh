# Portless routes are matched by the owning process's cwd, never branch-name guesses.
preview::route-owners() {
	local row pid hostname
	local -A hosts
	local -a pids
	while IFS=$'\t' read -r pid hostname; do
		[[ $pid == <-> && $pid -gt 0 && $hostname == *.localhost ]] || continue
		hosts[$pid]=$hostname
		pids+=("$pid")
	done <<<"$1"
	(($#pids)) || return 0
	while IFS= read -r row; do
		case $row in
		p*) pid=${row#p} ;;
		n*) [[ -n ${hosts[$pid]:-} ]] && printf '%s\t%s\n' "${row#n}" "$hosts[$pid]" ;;
		esac
	done < <(/usr/sbin/lsof -w -a -p "${(j:,:)pids}" -d cwd -Fn 2>/dev/null)
}

preview::select-routes() {
	local root=$1 owners=$2 directory hostname
	while IFS=$'\t' read -r directory hostname; do
		[[ $directory == "$root" || $directory == "$root"/* ]] || continue
		[[ $directory == */.git/* ]] && continue
		while [[ $directory != / && ! -e $directory/.git ]]; do
			directory=${directory:h}
		done
		[[ $directory == "$root" ]] && print -r -- "$hostname"
	done <<<"$owners"
	return 0
}

preview::urls() {
	local root=$1 state=${PORTLESS_STATE_DIR:-$HOME/.portless}
	[[ -n $root && -r $state/routes.json ]] || return 0
	local routes owners hostname scheme=http port=80 suffix=""
	routes=$(jq -r '.[] | select(.pid > 0) | [.pid, .hostname] | @tsv' "$state/routes.json") || return
	owners=$(preview::route-owners "$routes")
	[[ -e $state/proxy.tls ]] && {
		scheme=https
		port=443
	}
	[[ -r $state/proxy.port ]] && port=$(<"$state/proxy.port")
	[[ $scheme:$port == http:80 || $scheme:$port == https:443 ]] || suffix=":$port"
	while IFS= read -r hostname; do
		[[ -n $hostname ]] && print -r -- "$scheme://$hostname$suffix"
	done < <(preview::select-routes "$root" "$owners")
}

# The dev family's own record for this checkout: the route it registered and the
# pid that owns it. Matching portless's routes.json by cwd cannot work here — the
# family runs portless from the cache dir on purpose, so the registered pid's cwd
# is never the checkout — but its pidfile names the route exactly.
preview::dev-url() {
	local root=$1 cache name pidfile pid route state=${PORTLESS_STATE_DIR:-$HOME/.portless}
	[[ -n $root ]] || return 0
	cache="${XDG_CACHE_HOME:-$HOME/.cache}/dev-profile/dev"
	name=${(L)root:t}
	name=${name//[^a-z0-9]/-}
	while [[ $name == *--* ]]; do name=${name//--/-}; done
	name=${name##-}
	name=${name%%-}
	pidfile="${cache}/${name}.pid"
	[[ -s $pidfile ]] || return 0
	pid=$(sed -n 1p "$pidfile")
	route=$(sed -n 3p "$pidfile")
	[[ -n $pid && -n $route ]] || return 0
	kill -0 "$pid" 2>/dev/null || return 0
	local scheme=http port=80 suffix=""
	[[ -e $state/proxy.tls ]] && {
		scheme=https
		port=443
	}
	[[ -r $state/proxy.port ]] && port=$(<"$state/proxy.port")
	[[ $scheme:$port == http:80 || $scheme:$port == https:443 ]] || suffix=":$port"
	print -r -- "$scheme://${route}.localhost${suffix}"
}

# The dev family's record when it has one, else a cwd-matched portless route (a
# stack started by hand outside the family).
preview::selected-urls() {
	local own
	own=$(preview::dev-url "$1")
	[[ -n $own ]] && {
		print -r -- "$own"
		return 0
	}
	preview::urls "$1"
}
