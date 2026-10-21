#!/usr/bin/env bash
# Contract fixtures for task rendering and the formatter wrappers the tasks call.
# Usage: tasks.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' output=''
. "$(dirname "$0")/world.sh" "$@"

# mise renders a task script through Tera only when the task runs, so `mise tasks`
# passes on a script Tera rejects (a `${#array[@]}` reads as a comment opener).
# A dry run renders every task without executing it.
fixture_every_task_renders() {
	local repo task
	repo="$(new_repo task-render)"
	(cd "$repo" && mise tasks ls --json | jq -r '.[].name') >"${work}/task-names.txt" ||
		fail "task render: could not list tasks"
	[[ -s "${work}/task-names.txt" ]] || fail "task render: the overlay defines no tasks"
	while IFS= read -r task; do
		(cd "$repo" && mise run -n "$task") >"$output" 2>&1 || fail "task render: '${task}' does not load"
	done <"${work}/task-names.txt"
}

# Real rustfmt. Bare rustfmt assumes edition 2015, which sorts imports differently
# from `cargo fmt` on a 2024 crate; the wrapper must agree with the crate's edition.
fixture_rustfmt_follows_crate_edition() {
	local repo
	repo="$(new_repo rust-edition)"
	mkdir -p "${repo}/src"
	printf '[package]\nname = "fixture"\nversion = "0.1.0"\nedition = "2024"\n' >"${repo}/Cargo.toml"
	printf 'use std::collections::{HashMap, hash_map};\n\nfn main() {}\n' >"${repo}/src/main.rs"
	cp "${repo}/src/main.rs" "${work}/main.before"

	(cd "$work" && dev-profile-rustfmt --stdin-path "${repo}/src/main.rs" <"${work}/main.before") >"${work}/main.stdin" 2>"$output" ||
		fail "rustfmt: stdin mode failed"
	cmp -s "${work}/main.before" "${work}/main.stdin" || fail "rustfmt: stdin mode reformatted a 2024-formatted file"

	(cd "$work" && dev-profile-rustfmt "${repo}/src/main.rs") >"$output" 2>&1 || fail "rustfmt: file mode failed"
	cmp -s "${work}/main.before" "${repo}/src/main.rs" || fail "rustfmt: file mode reformatted a 2024-formatted file"
}

fixture_every_task_renders
fixture_rustfmt_follows_crate_edition
echo "contract task fixtures ok"
