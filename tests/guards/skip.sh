#!/usr/bin/env bash
# Guard fixtures for what the profile deliberately skips: lockfiles and vendored
# trees. Usage: skip.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work=''
. "$(dirname "$0")/world.sh" "$@"

# Valid YAML that dprint reformats and a strict yamllint rejects.
lockfile_yaml='lockfileVersion: 9
importers:   {a:   1}
'

# Rejected by `braces: {max-spaces-inside: 0}`.
yamllint_rejected_yaml='importers: { a: 1 }
'

fixture_dprint_leaves_lockfile_unchanged() {
	local repo
	repo="$(new_repo lockfile-dprint)"
	printf '%s' "$lockfile_yaml" >"${repo}/pnpm-lock.yaml"
	git -C "$repo" add pnpm-lock.yaml
	commit_hook "$repo" || fail "lockfile dprint: must pass"
	[[ "$(git -C "$repo" show :pnpm-lock.yaml)" == "${lockfile_yaml%$'\n'}" ]] ||
		fail "lockfile dprint: the staged lockfile must not be reformatted"
}

fixture_yamllint_skips_lockfile() {
	command -v yamllint >/dev/null 2>&1 || return 0
	local repo
	repo="$(new_repo lockfile-yamllint)"
	# A project config wins over any user-level one, so the rule is not machine-dependent.
	printf 'rules:\n  braces: {max-spaces-inside: 0}\n' >"${repo}/.yamllint"
	printf '%s' "$yamllint_rejected_yaml" >"${repo}/pnpm-lock.yaml"
	printf '%s' "$yamllint_rejected_yaml" >"${repo}/ordinary.yaml"
	# Plumbing makes the base commit pre-push diffs against, with no hooks involved.
	git -C "$repo" update-ref HEAD "$(GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.com GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.com git -C "$repo" commit-tree -m init "$(git -C "$repo" hash-object -t tree -w /dev/null)")"
	git -C "$repo" add pnpm-lock.yaml ordinary.yaml
	if (cd "$repo" && HK_CONFIG_DIR="${work}/hk-config" hk check --slow --staged -S yamllint) >"${work}/output.txt" 2>&1; then
		fail "lockfile yamllint: the control yaml file must fail yamllint"
	fi
	if grep -q 'pnpm-lock.yaml' "${work}/output.txt"; then fail "lockfile yamllint: the lockfile must be skipped"; fi
	grep -q 'ordinary.yaml' "${work}/output.txt" || fail "lockfile yamllint: the control file must be judged"
}

# Vendored trees are never ours to judge: staged `go mod vendor` output must not
# trip a step. The same content outside a vendored directory still must.
fixture_vendored_paths_are_skipped() {
	local repo dir
	for dir in vendor node_modules third_party .venv sub/vendor; do
		repo="$(new_repo "vendored-${dir//\//-}")"
		mkdir -p "${repo}/${dir}/x"
		printf '# Log\n\n## v1\n\n## v1\n' >"${repo}/${dir}/x/CHANGELOG.md"
		head -c 2000000 /dev/zero | tr '\0' 'a' >"${repo}/${dir}/x/big.bin"
		# -f: a global gitignore commonly names node_modules and .venv.
		git -C "$repo" add -f "$dir"
		push_check "$repo" check-added-large-files || fail "vendored ${dir}: staged files must be skipped"
	done
	repo="$(new_repo vendored-lookalike)"
	mkdir -p "${repo}/lib/x"
	head -c 2000000 /dev/zero | tr '\0' 'a' >"${repo}/lib/x/big.bin"
	git -C "$repo" add lib
	expect_blocked "$repo" check-added-large-files "large file outside a vendored directory"
}

fixture_strict_json() {
	local repo name
	repo="$(new_repo strict-json)"
	printf '{"a":1,}\n' >"${repo}/trailing.json"
	git -C "$repo" add trailing.json
	expect_blocked "$repo" strict-json "trailing comma in .json"

	repo="$(new_repo strict-json-comment)"
	printf '{"a":1 // c\n}\n' >"${repo}/comment.json"
	git -C "$repo" add comment.json
	expect_blocked "$repo" strict-json "comment in .json"

	repo="$(new_repo strict-json-lenient)"
	mkdir -p "${repo}/.vscode" "${repo}/.devcontainer/x" "${repo}/zed"
	for name in x.jsonc tsconfig.json tsconfig.app.json jsconfig.json .vscode/settings.json .devcontainer/x/devcontainer.json zed/private_settings.json; do
		printf '{"a":1 // c\n,}\n' >"${repo}/${name}"
	done
	printf '{"a": 1}\n' >"${repo}/ok.json"
	git -C "$repo" add .
	push_check "$repo" strict-json || fail "lenient JSON files and valid .json: must pass"
}

fixture_dprint_leaves_lockfile_unchanged
fixture_yamllint_skips_lockfile
fixture_vendored_paths_are_skipped
fixture_strict_json
echo "guard skip fixtures ok"
