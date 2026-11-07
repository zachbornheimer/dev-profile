#!/usr/bin/env bash
# The global uv cooldown (`exclude-newer = "3 days"`) makes `uv lock --check` and
# `uv run --locked` refuse a lock that predates it, though nothing in the lock is
# out of date. dev-profile-uv-lock-cooldown records the cooldown in such a lock
# without moving a pin, with the cooldown still on. Real uv, no network: the
# projects have no dependencies from an index.
# Usage: uv-lock-cooldown-fixture.sh <profile-root>
set -euo pipefail

root="${1:?usage: uv-lock-cooldown-fixture.sh <profile-root>}"
heal="${root}/bin/dev-profile-uv-lock-cooldown"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL uv-lock-cooldown fixture: $*" >&2
	exit 1
}

command -v uv >/dev/null 2>&1 || fail "uv is not installed"

# The policy under test: the same line the global uv config carries.
printf 'exclude-newer = "3 days"\n' >"${work}/uv.toml"
export UV_CONFIG_FILE="${work}/uv.toml"

new_project() {
	local dir="${work}/$1"
	mkdir -p "${dir}"
	git -C "${dir}" init -q
	printf '[project]\nname = "fixture"\nversion = "0.1.0"\nrequires-python = ">=3.12"\ndependencies = []\n' >"${dir}/pyproject.toml"
	echo "${dir}"
}

# A lock written before the cooldown existed: no record of it.
lock_without_cooldown() {
	(cd "$1" && env -u UV_CONFIG_FILE UV_NO_CONFIG=1 uv lock >/dev/null 2>&1)
	grep -q 'exclude-newer' "$1/uv.lock" && fail "$1: a lock written without config records the cooldown"
	return 0
}

run_heal() {
	local dir="$1"
	shift
	(cd "${dir}" && "${heal}" "$@" 2>&1)
}

check_passes() {
	(cd "$1" && uv lock --check >/dev/null 2>&1)
}

fixture_heals_a_lock_that_predates_the_cooldown() {
	local dir out
	dir="$(new_project predates)"
	lock_without_cooldown "${dir}"
	# Red: the failure the pre-push test run hit.
	if check_passes "${dir}"; then fail "predates: uv lock --check passed before the heal, so the fixture reproduces nothing"; fi
	out="$(cd "${dir}" && uv lock --check 2>&1 || true)"
	grep -q 'due to addition of global exclude newer' <<<"${out}" || fail "predates: uv names another reason: ${out}"
	# Green.
	run_heal "${dir}" >/dev/null || fail "predates: heal failed"
	check_passes "${dir}" || fail "predates: uv lock --check still fails after the heal"
	(cd "${dir}" && uv sync --locked --dry-run >/dev/null 2>&1) || fail "predates: uv sync --locked still fails after the heal"
	grep -q 'exclude-newer-span = "P3D"' "${dir}/uv.lock" || fail "predates: the lock does not record the cooldown"
	# Idempotent: a lock that records it is not rewritten.
	cat "${dir}/uv.lock" >"${work}/before"
	run_heal "${dir}" >/dev/null || fail "predates: second heal failed"
	cmp -s "${work}/before" "${dir}/uv.lock" || fail "predates: a lock that records the cooldown was rewritten"
}

fixture_named_files_find_their_lock() {
	local dir
	dir="$(new_project nested)"
	mkdir -p "${dir}/svc/src"
	mv "${dir}/pyproject.toml" "${dir}/svc/pyproject.toml"
	lock_without_cooldown "${dir}/svc"
	run_heal "${dir}" svc/src/main.py >/dev/null || fail "nested: heal failed"
	check_passes "${dir}/svc" || fail "nested: the lock above a named file was not healed"
}

# The heal must never hide a real difference: a relock that moves a pin is put
# back, and the cooldown stays on.
fixture_refuses_to_move_a_pin() {
	local dir out status=0
	dir="$(new_project moves)"
	lock_without_cooldown "${dir}"
	sed -i.bak 's/^version = "0.1.0"/version = "0.0.9"/' "${dir}/uv.lock"
	rm -f "${dir}/uv.lock.bak"
	cat "${dir}/uv.lock" >"${work}/stale"
	out="$(run_heal "${dir}")" || status=$?
	[[ "${status}" -ne 0 ]] || fail "moves: a heal that moves a pin passed: ${out}"
	cmp -s "${work}/stale" "${dir}/uv.lock" || fail "moves: the lock was not put back"
}

fixture_leaves_other_staleness_alone() {
	local dir
	dir="$(new_project other)"
	(cd "${dir}" && uv lock >/dev/null 2>&1)
	printf '[project]\nname = "fixture"\nversion = "0.2.0"\nrequires-python = ">=3.12"\ndependencies = []\n' >"${dir}/pyproject.toml"
	if check_passes "${dir}"; then fail "other: the lock is not stale; the fixture reproduces nothing"; fi
	cat "${dir}/uv.lock" >"${work}/snap-other"
	run_heal "${dir}" >/dev/null || fail "other: a lock stale for another reason failed the heal"
	cmp -s "${work}/snap-other" "${dir}/uv.lock" || fail "other: a lock stale for another reason was rewritten"
}

fixture_heals_a_lock_that_predates_the_cooldown
fixture_named_files_find_their_lock
fixture_refuses_to_move_a_pin
fixture_leaves_other_staleness_alone
echo "uv-lock-cooldown fixture ok"
