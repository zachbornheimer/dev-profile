#!/usr/bin/env bash
set -euo pipefail
# Edit tools/repo/hardcoded-dev-port.sh: `mise run generate` copies it into bin/.
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../lib/facts.sh"

# Pre-push judge: no hardcoded dev port added to app code (added lines only). A file that reads PORT from
# the environment may keep a literal as its fallback default.
(($#)) || exit 0

# Where the app's own server binds. One ERE per line: a bind address, a listen
# address string, .listen(<port>), PORT=<port>. Always judged.
listen_sites() {
	cat <<'EOF'
0\.0\.0\.0:[0-9]{4,5}([^0-9]|$)
["'`]:[0-9]{4,5}["'`]
\.listen\([[:space:]]*[0-9]{4,5}
(^|[^[:alnum:]_])PORT=["']?[0-9]{2,5}
EOF
}

# A client-side address. It is the app's own only when the repo serves that
# port; otherwise it names another service (Ollama, a memory API, a proxy).
client_address() {
	echo '(127\.0\.0\.1|localhost):[0-9]{4,5}([^0-9]|$)'
}

# An env read whose fallback is on the same line: the literal is configurable.
env_fallbacks() {
	cat <<'EOF'
\$\{[A-Za-z_][A-Za-z0-9_]*:?[-=]
[Ee][Nn][Vv](\.[A-Za-z_][A-Za-z0-9_]*|\[["'][A-Za-z_][A-Za-z0-9_]*["']\])[[:space:]]*(\?\?|\|\|)
ENV\{[A-Za-z_][A-Za-z0-9_]*\}[[:space:]]*(//|\|\|)
[Gg]etenv\([^)]*\)[[:space:]]*(\?\?|\?:|\|\||or[[:space:]])
[A-Za-z_.]*[Ee][Nn][Vv][A-Za-z_.]*\([[:space:]]*["'][A-Z][A-Z0-9_]*["'][[:space:]]*,
EOF
}

# Ports most dev servers default to: a URL on one is taken as the app's own
# even when no listen site in the repo names it.
conventional_dev_ports() {
	printf '%s\n' 3000 3001 4000 4200 4321 5000 5173 5174 8000 8080 8081 8888 9000
}

# A compose file's published port, "<host>:<container>".
compose_ports() {
	cat <<'EOF'
^[[:space:]]*-?[[:space:]]*["']?[0-9]{4,5}:[0-9]{2,5}(/[a-z]+)?["']?[[:space:]]*(#.*)?$
EOF
}

# The ways code reads PORT from its environment.
reads_port() {
	cat <<'EOF'
process\.env\.PORT
env\.PORT
[Gg]etenv\(["']PORT["']
LookupEnv\(["']PORT["']
environ(\.get)?[\[(]["']PORT["']
ENV(\.fetch)?[\[(]["']PORT["']
env\(["']PORT["']
\$\{?PORT([^[:alnum:]_]|$)
EOF
}

# "<base> <tip>" per pushed ref. In a push, SAH_PUSH_REFS names the saved
# pre-push stdin ("<local ref> <local sha> <remote ref> <remote sha>"); a
# new branch, or a remote tip this clone lacks, diffs from the merge-base
# with the default branch. Outside a push: merge-base of HEAD.
empty_tree="$(git hash-object -t tree /dev/null)"
default_base() { # <tip>
	local ref
	for ref in origin/HEAD origin/main origin/master; do
		if git rev-parse -q --verify "${ref}^{commit}" >/dev/null; then
			git merge-base "$1" "${ref}" 2>/dev/null && return 0
		fi
	done
	echo "${empty_tree}"
}
ranges() {
	local all_zeros='^0+$' _lref local_sha _rref remote_sha
	if [[ -n "${SAH_PUSH_REFS:-}" && -r "${SAH_PUSH_REFS}" ]]; then
		while read -r _lref local_sha _rref remote_sha; do
			[[ -n "${local_sha:-}" ]] || continue
			if [[ "${local_sha}" =~ ${all_zeros} ]]; then continue; fi
			if [[ "${remote_sha}" =~ ${all_zeros} ]] || ! git cat-file -e "${remote_sha}^{commit}" 2>/dev/null; then
				echo "$(default_base "${local_sha}") ${local_sha}"
			else
				echo "${remote_sha} ${local_sha}"
			fi
		done <"${SAH_PUSH_REFS}"
	else
		echo "$(default_base HEAD) HEAD"
	fi
}
# "<line>:<text>" for each line the push adds to <file>.
added_lines() { # <file>
	local base tip
	while read -r base tip; do
		git diff -U0 --no-color --no-ext-diff "${base}" "${tip}" -- "$1" | awk '
      /^@@/ { split($3, a, ","); n = substr(a[1], 2) + 0; next }
      /^\+\+\+/ { next }
      /^\+/ { print n ":" substr($0, 2); n++ }
    '
	done < <(ranges) | sort -t: -k1,1n -u
}

# Every port this repo's own server takes: the conventional dev ports plus
# each port a tracked, non-test file listens on or publishes from compose.
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# git pathspecs that keep own_ports from learning a port out of a test or doc:
# PROFILE_NOT_APP_CODE (lib/facts.sh) holds one glob per line.
not_app_code=()
while IFS= read -r glob; do
	not_app_code+=(":(exclude,glob)${glob}")
done <<<"${PROFILE_NOT_APP_CODE:?}"
own_ports() {
	conventional_dev_ports
	{
		git -C "${repo_root}" grep -hIoE -e "$(listen_sites | paste -sd'|' -)" -e '--port[= ][0-9]{4,5}' \
			-- . "${not_app_code[@]}" || true
	} | grep -oE '[0-9]{4,5}' || true
	{
		git -C "${repo_root}" grep -hIoE -e "$(compose_ports)" -- '*compose*.yml' '*compose*.yaml' \
			"${not_app_code[@]}" || true
	} | grep -oE '[0-9]{4,5}:' | tr -d ':' || true
}

# Lines (stdin, "<line>:<text>") naming localhost:<port> where the repo serves <port>.
served_addresses() {
	local l
	while IFS= read -r l; do
		if grep -oE -e "$(client_address)" <<<"${l#*:}" | grep -oE '[0-9]{4,5}' | grep -qxFf <(echo "${own}"); then
			echo "${l}"
		fi
	done < <(grep -E -e "^[0-9]+:.*($(client_address))" || true)
}

hits_in() {
	local file="$1" added candidates
	added="$(added_lines "${file}")"
	[[ -n "${added}" ]] || return 0
	candidates="$(grep -vE -e "^[0-9]+:.*($(env_fallbacks | paste -sd'|' -))" <<<"${added}" || true)"
	[[ -n "${candidates}" ]] || return 0
	{
		grep -E -e "^[0-9]+:.*($(listen_sites | paste -sd'|' -))" <<<"${candidates}" || true
		served_addresses <<<"${candidates}"
		case "${file##*/}" in
		*compose*.yml | *compose*.yaml)
			while IFS= read -r l; do
				grep -qE -e "$(compose_ports)" <<<"${l#*:}" && echo "${l}"
			done <<<"${candidates}" || true
			;;
		esac
	} | sort -t: -k1,1n -u
}

own="$(own_ports)"
status=0
for file in "$@"; do
	[[ -f "${file}" ]] || continue
	if grep -qIE -e "$(reads_port)" -- "${file}"; then continue; fi
	hits="$(hits_in "${file}")"
	[[ -n "${hits}" ]] || continue
	while IFS= read -r hit; do
		echo "${file}:${hit}" >&2
	done <<<"${hits}"
	status=1
done

if [[ "${status}" -ne 0 ]]; then
	echo "hardcoded dev port: read \$PORT from the environment (a literal fallback default is fine) and run the app with PORT set per checkout (e.g. through 'mise run dev')." >&2
fi
exit "${status}"
