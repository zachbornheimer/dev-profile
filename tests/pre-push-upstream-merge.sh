#!/usr/bin/env bash
# A push whose branch merged upstream is judged on what the push wrote, not on
# upstream's own lines: the lint findings that arrive with the merge must not
# block it, while a finding the pusher's own commit introduces still must.
#
# The profile's hk config, active the way bootstrap links it, run through the
# real pre-push path (dev-profile-pre-push, which is what hands the pushed refs
# to the steps). Only the steps this fixture judges run, so another step's
# verdict on the fixture's files cannot decide it.
set -euo pipefail
command -v markdownlint >/dev/null 2>&1 || exit 0
command -v betterleaks >/dev/null 2>&1 || exit 0

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL pre-push-upstream-merge: $*" >&2
	[[ ! -f "${scratch}/push.txt" ]] || sed 's/^/  | /' "${scratch}/push.txt" >&2
	exit 1
}

mkdir -p "${scratch}/hk-config"
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"
steps="-S markdownlint -S markdownlint-fix -S betterleaks -S gitleaks"
command -v oxlint >/dev/null 2>&1 && steps="$steps -S oxlint -S oxlint-fix"
command -v dprint >/dev/null 2>&1 && steps="$steps -S dprint"
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = PATH="%s/bin:${PATH}" dev-profile-pre-push %s\n' \
	"${repo}" "$steps" >"${scratch}/gitconfig"
printf '[user]\n\tname = fixture\n\temail = fixture@example.invalid\n[commit]\n\tgpgsign = false\n' \
	>"${scratch}/plain-gitconfig"
export HK_CONFIG_DIR="${scratch}/hk-config" GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE DEV_PROFILE_PUSH_REFS

commit() { # <message>
	git -C "${scratch}/work" add -A
	git -C "${scratch}/work" commit -qm "$1"
}
push() { # <git args...>
	(cd "${scratch}/work" && git "$@") >"${scratch}/push.txt" 2>&1
}
setup() { # <git args...> — building the fixture's remotes installs no hook
	(cd "${scratch}/work" && GIT_CONFIG_GLOBAL="${scratch}/plain-gitconfig" git "$@")
}

git init -q --bare "${scratch}/upstream.git"
git init -q --bare "${scratch}/fork.git"
git init -q -b main "${scratch}/work"
git -C "${scratch}/work" remote add origin "${scratch}/fork.git"
git -C "${scratch}/work" remote add upstream "${scratch}/upstream.git"

# The fork's main: the fork's own work, with no markdown config of its own.
printf '# Fork\n\nfork notes\n' >"${scratch}/work/README.md"
# oxlint's local config pins the one rule this fixture judges, so it does not
# depend on which rules a default run enables.
printf '{\n  "rules": {\n    "no-debugger": "error"\n  }\n}\n' >"${scratch}/work/.oxlintrc.json"
# dprint's local config pins the fixture's judgement to one cached plugin, so
# the step judges these files and not the machine's global config; it is inert
# when dprint is not installed, because the step is then not selected.
printf '{\n  "plugins": ["npm:@dprint/json@0.25.2"],\n  "includes": ["**/*.json"]\n}\n' >"${scratch}/work/dprint.json"
commit "docs: fork readme"
setup push -q origin main
setup fetch -q origin
# The pushed remote's default branch, as a clone would set it.
git -C "${scratch}/work" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main

# Upstream's line: a changelog that repeats its section headings (MD024) and a
# prompt doc whose first fence has no language (MD040). Both are upstream's own
# content, and upstream's own CI accepts it.
git -C "${scratch}/work" switch -q -c upstream main
mkdir -p "${scratch}/work/docs"
printf '# Changelog\n\n## Changed\n\n- one\n\n## Changed\n\n- two\n' >"${scratch}/work/CHANGELOG.md"
printf '```\nno language\n```\n\nprompt text\n' >"${scratch}/work/docs/prompt.md"
# Upstream also ships what a fixer cannot heal: a debugger statement oxlint
# leaves in place, and JSON dprint cannot parse.
mkdir -p "${scratch}/work/scripts"
printf 'function upstream() {\n  debugger;\n}\n' >"${scratch}/work/scripts/upstream.js"
printf '{"broken"\n' >"${scratch}/work/broken.json"
commit "docs: upstream changelog and prompt"
setup push -q upstream upstream:main
setup fetch -q upstream
git -C "${scratch}/work" switch -q main

# The topic branch: the pusher's own commit, published at the fork, then upstream merged in.
git -C "${scratch}/work" switch -q -c topic
printf 'topic\n' >"${scratch}/work/topic.txt"
commit "feat: topic work"
setup push -q origin topic
setup fetch -q origin
git -C "${scratch}/work" merge -q --no-edit upstream/main

# Control: the merged tree really does carry upstream's own findings, so the pass
# below is the attribution working and not the findings being absent.
if (cd "${scratch}/work" && markdownlint CHANGELOG.md docs/prompt.md) >/dev/null 2>&1; then
	fail "control: upstream's own findings must be present in the merged tree"
fi
if command -v oxlint >/dev/null 2>&1; then
	if (cd "${scratch}/work" && oxlint scripts/upstream.js) >/dev/null 2>&1; then
		fail "control: upstream's own oxlint finding must be present in the merged tree"
	fi
fi
if command -v dprint >/dev/null 2>&1; then
	if (cd "${scratch}/work" && dprint check broken.json) >/dev/null 2>&1; then
		fail "control: upstream's own dprint finding must be present in the merged tree"
	fi
fi

# 1. The upstream merge below the tip, on a branch published nowhere: the
# published parent that must be attributed is the merge commit's, several
# commits down the push range — not the pushed tip's. Upstream's findings
# arrive with that merge and must not block the push.
git -C "${scratch}/work" switch -q -c above
printf 'above\n' >"${scratch}/work/above.txt"
commit "feat: work above the merge"
if ! push push -q origin above; then
	fail "an above-the-merge push must pass the hook"
fi

# 2. The upstream-merge push passes.
if ! push push -q origin topic; then
	fail "an upstream-merge push must pass the hook"
fi
grep -q 'markdownlint' "${scratch}/push.txt" || fail "the markdownlint step must have run"
if command -v oxlint >/dev/null 2>&1 && ! grep -q 'oxlint' "${scratch}/push.txt"; then
	fail "the oxlint step must have run"
fi
if command -v dprint >/dev/null 2>&1 && ! grep -q 'dprint' "${scratch}/push.txt"; then
	fail "the dprint step must have run"
fi

# 3. A push spelled with a repository path instead of a remote name: git hands
# the hook the path as the remote, from which no remote-tracking ref can be
# derived. The push base the hook computes itself must carry the from-ref.
git init -q --bare "${scratch}/probe.git"
if ! push push -q "${scratch}/probe.git" above:refs/heads/probe; then
	fail "a path-remote push must pass the hook"
fi

# 4. A finding the pusher's own commit introduces still blocks.
git -C "${scratch}/work" switch -q -c authored
printf '```\nno language\n```\n' >"${scratch}/work/authored.md"
commit "docs: add authored prompt"
if push push -q origin authored; then
	fail "a markdown finding this push introduces must fail the hook"
fi
grep -q '✗ markdownlint' "${scratch}/push.txt" || fail "the markdownlint step must be the one that fails"
grep -q 'MD040' "${scratch}/push.txt" || fail "the introduced finding must be reported"

# 4b. An oxlint error the pusher's own commit introduces still blocks.
if command -v oxlint >/dev/null 2>&1; then
	git -C "${scratch}/work" switch -q topic
	git -C "${scratch}/work" switch -q -c authored-js
	printf 'function authored() {\n  debugger;\n}\n' >"${scratch}/work/authored.js"
	commit "feat: add authored debugger"
	if push push -q origin authored-js; then
		fail "an oxlint finding this push introduces must fail the hook"
	fi
	grep -q '✗ oxlint' "${scratch}/push.txt" || fail "the oxlint step must be the one that fails"
	grep -q 'no-debugger' "${scratch}/push.txt" || fail "the introduced oxlint finding must be reported"
fi

# 4c. A file dprint cannot parse, introduced by the pusher's own commit, still
# blocks: a formatter cannot heal it, so the finding is the pusher's answer.
if command -v dprint >/dev/null 2>&1; then
	git -C "${scratch}/work" switch -q topic
	git -C "${scratch}/work" switch -q -c authored-json
	printf '{"authored"\n' >"${scratch}/work/authored.json"
	commit "feat: add authored json"
	if push push -q origin authored-json; then
		fail "an unparseable file this push introduces must fail the hook"
	fi
	grep -q '✗ dprint' "${scratch}/push.txt" || fail "the dprint step must be the one that fails"
fi

# 5. The security steps still cover the pushed range: an authored secret fails.
git -C "${scratch}/work" switch -q -c leaked
printf "curl -H 'authorization: Bearer %s' https://api.example.invalid\n" \
	"7f3c9a1e5b2d8f4a6c0e9b3d7a1f5c8e2b4d6a9f" >"${scratch}/work/notes.sh"
commit "feat: add notes"
if push push -q origin leaked; then
	fail "an authored secret must fail the hook"
fi
grep -qE '✗ (betterleaks|gitleaks)' "${scratch}/push.txt" || fail "a security step must be the one that fails"

echo "ok pre-push-upstream-merge"
