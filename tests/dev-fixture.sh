#!/usr/bin/env bash
# dev-profile-dev and dev-profile-caddy: name derivation (main checkout vs linked
# worktree), the port each gets, the Caddy snippet's life, and the Caddy calls.
# Caddy, workz and curl are stubs, so no fixture starts a proxy.
# Usage: dev-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: dev-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
export HK=0

fail() {
	echo "FAIL dev fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

stubs="${work}/stubs"
state="${work}/caddy-state"
ctl_log="${work}/ctl.log"
caddy_log="${work}/caddy.log"
mkdir -p "$stubs"

# workz: a fixed port per worktree directory, in workz's JSON shape.
cat >"${stubs}/workz" <<'EOF'
#!/usr/bin/env bash
case "${PWD##*/}" in
	*fix-login*) port=5550 ;;
	*) port=5560 ;;
esac
echo "{\"isolation\":{\"port\":${port},\"port_count\":10}}"
EOF
# The dev-profile-caddy stand-in the wrapper calls.
cat >"${stubs}/ctl" <<EOF
#!/usr/bin/env bash
echo "\$*" >>"${ctl_log}"
EOF
# caddy, curl (the admin API probe; CURL_UP=1 means Caddy answers) and security (CA trust).
cat >"${stubs}/caddy" <<EOF
#!/usr/bin/env bash
echo "caddy \$*" >>"${caddy_log}"
EOF
cat >"${stubs}/curl" <<'EOF'
#!/usr/bin/env bash
[[ "${CURL_UP:-}" == 1 ]]
EOF
printf '#!/usr/bin/env bash\nexit 1\n' >"${stubs}/security"
chmod +x "${stubs}"/*

export PATH="${stubs}:${out}/bin:${PATH}"
export DEV_PROFILE_CADDY_DIR="$state"
export DEV_PROFILE_CADDY_CTL="${stubs}/ctl"

git_fixture() {
	git -C "$1" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false -c core.hooksPath=/dev/null "${@:2}"
}

new_repo() {
	local dir="${work}/$1"
	mkdir -p "$dir"
	git -C "$dir" init -q -b main
	git_fixture "$dir" commit -q --allow-empty -m init
	echo "$dir"
}

plan() {
	(cd "$1" && shift && dev-profile-dev --plan "$@") >"${work}/output.txt" 2>&1
}

expect_plan_name() {
	plan "$1" || fail "$3: --plan failed"
	[[ "$(cut -d' ' -f1 "${work}/output.txt")" == "$2" ]] || fail "$3: expected name '$2', got '$(cat "${work}/output.txt")'"
}

fixture_main_checkout_is_named_for_the_repo() {
	local repo port
	repo="$(new_repo MyApp)"
	expect_plan_name "$repo" myapp "main checkout"
	port="$(cut -d' ' -f2 "${work}/output.txt")"
	((port >= 20000 && port <= 29999)) || fail "main checkout: port ${port} is outside 20000-29999"
	plan "$repo" --name "Other App" || fail "--name: failed"
	[[ "$(cut -d' ' -f1 "${work}/output.txt")" == other-app ]] || fail "--name: not applied as a hostname label"
}

fixture_linked_worktree_is_named_slug_dot_repo() {
	local repo tree other plain
	repo="$(new_repo shop)"
	tree="${work}/shop-fix-login"
	git_fixture "$repo" worktree add -q -b feat/fix-login "$tree"
	expect_plan_name "$tree" fix-login.shop "linked worktree"
	[[ "$(cut -d' ' -f2 "${work}/output.txt")" == 5550 ]] || fail "linked worktree: PORT must be workz's allocation"
	other="${work}/shop-dark-mode"
	git_fixture "$repo" worktree add -q -b feat/dark-mode "$other"
	expect_plan_name "$other" dark-mode.shop "second worktree"
	[[ "$(cut -d' ' -f2 "${work}/output.txt")" == 5560 ]] || fail "second worktree: PORT must differ from the first"
	plain="${work}/scratch Tree"
	git_fixture "$repo" worktree add -q -b scratch "$plain"
	expect_plan_name "$plain" scratch-tree.shop "worktree without the repo prefix"
	expect_plan_name "$repo" shop "main checkout of a repo that has worktrees"
}

fixture_run_routes_then_cleans_up() {
	local repo snippet seen
	repo="$(new_repo routed)"
	snippet="${state}/sites/routed.caddy"
	: >"$ctl_log"
	seen="${work}/seen.txt"
	(cd "$repo" && dev-profile-dev -- bash -c "echo \"PORT=\${PORT}\" >'${seen}'; cp '${snippet}' '${work}/snippet.txt'") \
		>"${work}/output.txt" 2>&1 || fail "run: failed"
	[[ ! -e "$snippet" ]] || fail "run: the route snippet outlived the command"
	grep -qxF "dev: https://routed.localhost (PORT=$(sed -n 's/^PORT=//p' "$seen"))" "${work}/output.txt" || fail "run: the URL line is missing or has the wrong PORT"
	grep -qxF "routed.localhost {" "${work}/snippet.txt" || fail "run: snippet names the wrong host"
	grep -qxF "	tls internal" "${work}/snippet.txt" || fail "run: snippet lacks tls internal"
	grep -qxF "	reverse_proxy 127.0.0.1:$(sed -n 's/^PORT=//p' "$seen")" "${work}/snippet.txt" || fail "run: snippet proxies to a different port than the app's PORT"
	[[ "$(tr '\n' ' ' <"$ctl_log")" == "ensure reload " ]] || fail "run: expected Caddy ensure then reload, got: $(tr '\n' ' ' <"$ctl_log")"
}

fixture_run_passes_the_exit_status_through() {
	local repo status=0
	repo="$(new_repo failing)"
	(cd "$repo" && dev-profile-dev -- bash -c 'exit 7') >"${work}/output.txt" 2>&1 || status=$?
	[[ "$status" -eq 7 ]] || fail "exit status: expected 7, got ${status}"
	[[ ! -e "${state}/sites/failing.caddy" ]] || fail "exit status: the route stayed after a failing command"
}

fixture_signal_removes_the_route() {
	local repo pid
	repo="$(new_repo signalled)"
	(cd "$repo" && exec dev-profile-dev -- sleep 30) >"${work}/output.txt" 2>&1 &
	pid=$!
	for _ in $(seq 1 50); do
		[[ -e "${state}/sites/signalled.caddy" ]] && break
		sleep 0.1
	done
	[[ -e "${state}/sites/signalled.caddy" ]] || fail "signal: the route was never written"
	kill -TERM "$pid"
	wait "$pid" || true
	[[ ! -e "${state}/sites/signalled.caddy" ]] || fail "signal: the route stayed after SIGTERM"
}

fixture_a_live_route_is_not_taken_over() {
	local repo status=0
	repo="$(new_repo busy)"
	mkdir -p "${state}/sites"
	sleep 30 &
	local owner=$!
	printf '# pid %s\nbusy.localhost {\n}\n' "$owner" >"${state}/sites/busy.caddy"
	(cd "$repo" && dev-profile-dev -- true) >"${work}/output.txt" 2>&1 || status=$?
	kill "$owner" 2>/dev/null || true
	[[ "$status" -ne 0 ]] || fail "live route: a second start must fail"
	grep -qF "already served by process ${owner}" "${work}/output.txt" || fail "live route: the message must name the owner"
	grep -qF "# pid ${owner}" "${state}/sites/busy.caddy" || fail "live route: the first app's route was overwritten"
	rm -f "${state}/sites/busy.caddy"
	printf '# pid 999999\nbusy.localhost {\n}\n' >"${state}/sites/busy.caddy"
	(cd "$repo" && dev-profile-dev -- true) >"${work}/output.txt" 2>&1 || fail "stale route: a dead owner's route must be replaced"
}

fixture_caddy_starts_or_reloads() {
	: >"$caddy_log"
	rm -rf "$state"
	export DEV_PROFILE_CADDY_BIN="${stubs}/caddy"
	env -u DEV_PROFILE_CADDY_CTL dev-profile-caddy ensure >"${work}/output.txt" 2>&1 || fail "caddy ensure: failed"
	cmp -s "${out}/Caddyfile" "${state}/Caddyfile" || fail "caddy ensure: the rendered Caddyfile was not copied"
	grep -qxF "caddy start --config ${state}/Caddyfile --adapter caddyfile" "$caddy_log" || fail "caddy ensure: not running, so it must start"
	: >"$caddy_log"
	CURL_UP=1 dev-profile-caddy ensure >"${work}/output.txt" 2>&1 || fail "caddy ensure (running): failed"
	grep -qF "caddy reload --config ${state}/Caddyfile --adapter caddyfile --address " "$caddy_log" || fail "caddy ensure: running, so it must reload"
	: >"$caddy_log"
	dev-profile-caddy reload >"${work}/output.txt" 2>&1 || fail "caddy reload (stopped): failed"
	[[ ! -s "$caddy_log" ]] || fail "caddy reload: a stopped Caddy must not be started or reloaded"
	CURL_UP=1 dev-profile-caddy stop >"${work}/output.txt" 2>&1 || fail "caddy stop: failed"
	grep -qF "caddy stop --address " "$caddy_log" || fail "caddy stop: did not stop"
	if grep -qE "^caddy trust" "$caddy_log"; then fail "caddy: trusting the CA is the user's call"; fi
	unset DEV_PROFILE_CADDY_BIN
}

fixture_untrusted_ca_is_mentioned_once() {
	local count
	rm -rf "$state"
	export DEV_PROFILE_CADDY_BIN="${stubs}/caddy"
	dev-profile-caddy ensure >"${work}/output.txt" 2>&1 || fail "trust hint: ensure failed"
	dev-profile-caddy ensure >>"${work}/output.txt" 2>&1 || fail "trust hint: second ensure failed"
	count="$(grep -c 'run once\|Trust it once' "${work}/output.txt" || true)"
	[[ "$count" -eq 1 ]] || fail "trust hint: expected the hint once, saw ${count}"
	grep -qF "caddy trust" "${work}/output.txt" || fail "trust hint: must give the exact command"
	unset DEV_PROFILE_CADDY_BIN
}

fixture_missing_caddy_says_how_to_install() {
	local status=0
	mkdir -p "${work}/bare"
	for tool in bash cmp cp mkdir dirname curl; do ln -sf "$(command -v "$tool")" "${work}/bare/${tool}"; done
	env -u DEV_PROFILE_CADDY_BIN PATH="${work}/bare" "${out}/bin/dev-profile-caddy" ensure >"${work}/output.txt" 2>&1 || status=$?
	[[ "$status" -ne 0 ]] || fail "missing caddy: ensure must fail"
	grep -qF "mise install" "${work}/output.txt" || fail "missing caddy: must say how to install it"
}

fixture_main_checkout_is_named_for_the_repo
fixture_linked_worktree_is_named_slug_dot_repo
fixture_run_routes_then_cleans_up
fixture_run_passes_the_exit_status_through
fixture_signal_removes_the_route
fixture_a_live_route_is_not_taken_over
fixture_caddy_starts_or_reloads
fixture_untrusted_ca_is_mentioned_once
fixture_missing_caddy_says_how_to_install
echo "dev fixture ok"
