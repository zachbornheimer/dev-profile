#!/usr/bin/env bash
# dev-profile-new-findings blocks only the findings a change introduces: a finding
# the file already carried at a base the change was built on passes. The bases are
# the merge base with origin's default branch, the pushed refs' remote tips, and
# the parents of a pushed merge that are already on a remote — the upstream line a
# fork branch merged in, which the push did not write.
set -euo pipefail
command -v ruff >/dev/null 2>&1 || exit 0
command -v markdownlint >/dev/null 2>&1 || exit 0

src="$(cd "$(dirname "$0")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
fail() {
	echo "FAIL new-findings fixture: $*" >&2
	exit 1
}
export GIT_CONFIG_GLOBAL="$work/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "$GIT_CONFIG_GLOBAL" user.name fixture
git config --file "$GIT_CONFIG_GLOBAL" user.email fixture@example.invalid
git config --file "$GIT_CONFIG_GLOBAL" commit.gpgsign false

repo="$work/repo"
git init -q -b main "$repo"
cd "$repo"
gate() { "$src/bin/dev-profile-new-findings" "$@" >"$work/out" 2>&1; }

# Upstream's file already catches a blind exception (BLE001) and does nothing with it (S110).
printf 'def f():\n    try:\n        return 1\n    except Exception:\n        pass\n' >mod.py
git add mod.py
git commit -q -m upstream
git update-ref refs/remotes/origin/main HEAD
git switch -q -c feature

# An edit elsewhere in the file keeps the inherited findings and adds none.
printf 'def f():\n    try:\n        return 2\n    except Exception:\n        pass\n\n\nVALUE = 1\n' >mod.py
gate ruff mod.py || fail "inherited ruff findings must not block: $(cat "$work/out")"

# A second blind except is introduced by the change and blocks.
printf '\n\ndef g():\n    try:\n        return 3\n    except Exception:\n        pass\n' >>mod.py
if gate ruff mod.py; then fail "an introduced ruff finding must block"; fi
grep -q 'BLE001' "$work/out" || fail "the introduced finding must be printed: $(cat "$work/out")"
grep -q '2 finding(s) introduced' "$work/out" || fail "only the new findings count: $(cat "$work/out")"

# A repeated heading the base already carried is inherited, and one the change
# adds is a new duplicate that blocks.
git checkout -q -- mod.py
printf '# Title\n\n## Changed\n\n- one\n\n## Changed\n\n- two\n' >CHANGELOG.md
git add CHANGELOG.md
git commit -q -m changelog
git update-ref refs/remotes/origin/main HEAD
git switch -q -c docs
printf '# Title\n\n## Changed\n\n- one\n\n## Changed\n\n- two\n\n- three\n' >CHANGELOG.md
gate markdownlint CHANGELOG.md || fail "inherited markdown findings must not block: $(cat "$work/out")"
printf '# Title\n\n## Changed\n\n- one\n\n## Changed\n\n- two\n\n## Changed\n\n- three\n' >CHANGELOG.md
if gate markdownlint CHANGELOG.md; then fail "an introduced markdown finding must block"; fi
grep -q 'MD024' "$work/out" || fail "the introduced finding must be printed: $(cat "$work/out")"
git checkout -q -- CHANGELOG.md

# A line merged in from a parent that is already on a remote is upstream's, not
# the push's: it passes even though the push base never carried it. With that
# parent unpublished the same merge is the push's own work and blocks.
git switch -q main
git switch -q -c upstream-line
printf '# Upstream\n\n## Changed\n\n- one\n\n## Changed\n\n- two\n' >upstream.md
git add upstream.md
git commit -q -m upstream-headings
git update-ref refs/remotes/upstream/main HEAD
git switch -q main
git switch -q -c merged
printf 'topic\n' >topic.txt
git add topic.txt
git commit -q -m topic
git merge -q --no-edit upstream-line
printf 'refs/heads/merged %s refs/heads/merged %s\n' \
	"$(git rev-parse HEAD)" 0000000000000000000000000000000000000000 >"$work/refs"
export DEV_PROFILE_PUSH_REFS="$work/refs"
gate markdownlint upstream.md ||
	fail "a published parent's own findings must not block: $(cat "$work/out")"
git update-ref -d refs/remotes/upstream/main
if gate markdownlint upstream.md; then
	fail "control: an unpublished merged line is the push's own work and must block"
fi

# The pushed ref's own remote tip is a base too: findings a file already carried
# there are inherited debt, not this push's work.
git update-ref refs/remotes/upstream/main "$(git rev-parse upstream-line)"
git switch -q -c carried
printf 'more\n' >more.txt
git add more.txt
git commit -q -m more
printf 'refs/heads/carried %s refs/heads/carried %s\n' \
	"$(git rev-parse HEAD)" "$(git rev-parse merged)" >"$work/refs"
gate markdownlint upstream.md || fail "a remote tip's own findings must not block: $(cat "$work/out")"

# --fix runs the tool's own fixer and still blocks only what the change wrote.
gate --fix markdownlint upstream.md ||
	fail "--fix must pass when only inherited findings remain: $(cat "$work/out")"
printf '# Doc\n\n```\nno language\n```\n' >fixed.md
if gate --fix markdownlint fixed.md; then fail "--fix must still block an introduced finding"; fi
grep -q 'MD040' "$work/out" || fail "the introduced finding must be printed: $(cat "$work/out")"

# oxlint: an error the base already carried is inherited; one the change adds
# blocks. A comment carries the pusher's edit so the file differs from its base.
if command -v oxlint >/dev/null 2>&1; then
	git switch -q main
	git switch -q -c ox-upstream
	printf 'function f() {\n  debugger;\n}\n' >debug.js
	printf '{\n  "rules": {\n    "no-debugger": "error"\n  }\n}\n' >.oxlintrc.json
	git add .oxlintrc.json debug.js
	git commit -q -m debug-js
	git update-ref refs/remotes/origin/main HEAD
	git switch -q -c ox-edit
	printf '// the pusher touched the file\n' >>debug.js
	gate oxlint debug.js || fail "inherited oxlint findings must not block: $(cat "$work/out")"
	printf '\nfunction g() {\n  debugger;\n}\n' >>debug.js
	if gate oxlint debug.js; then fail "an introduced oxlint finding must block"; fi
	grep -q 'no-debugger' "$work/out" || fail "the introduced finding must be printed: $(cat "$work/out")"
	git checkout -q -- debug.js
fi

# dprint: a file the base already left unparseable is inherited debt; one the
# change introduces is its own finding. The local config pins one cached
# plugin so the judgement is the fixture's, not the machine's global config.
if command -v dprint >/dev/null 2>&1; then
	git switch -q main
	git switch -q -c dprint-upstream
	printf '{\n  "plugins": ["npm:@dprint/json@0.25.2"],\n  "includes": ["**/*.json"]\n}\n' >dprint.json
	printf '{"unformatted"\n' >unformatted.json
	git add dprint.json unformatted.json
	git commit -q -m dprint-files
	git update-ref refs/remotes/origin/main HEAD
	git switch -q -c dprint-edit
	gate dprint unformatted.json || fail "inherited dprint finding must not block: $(cat "$work/out")"
	printf '{"authored"\n' >authored.json
	if gate dprint authored.json; then fail "an introduced unparseable file must block"; fi
	grep -q 'unformatted' "$work/out" || fail "the introduced finding must be printed: $(cat "$work/out")"
fi

echo "ok new-findings fixture"
