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
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = PATH="%s/bin:${PATH}" dev-profile-pre-push -S markdownlint -S betterleaks -S gitleaks\n' \
	"${repo}" >"${scratch}/gitconfig"
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

# 1. The upstream-merge push passes.
if ! push push -q origin topic; then
	fail "an upstream-merge push must pass the hook"
fi
grep -q 'markdownlint' "${scratch}/push.txt" || fail "the markdownlint step must have run"

# 2. A finding the pusher's own commit introduces still blocks.
git -C "${scratch}/work" switch -q -c authored
printf '```\nno language\n```\n' >"${scratch}/work/authored.md"
commit "docs: add authored prompt"
if push push -q origin authored; then
	fail "a markdown finding this push introduces must fail the hook"
fi
grep -q '✗ markdownlint' "${scratch}/push.txt" || fail "the markdownlint step must be the one that fails"
grep -q 'MD040' "${scratch}/push.txt" || fail "the introduced finding must be reported"

# 3. The security steps still cover the pushed range: an authored secret fails.
git -C "${scratch}/work" switch -q -c leaked
printf "curl -H 'authorization: Bearer %s' https://api.example.invalid\n" \
	"7f3c9a1e5b2d8f4a6c0e9b3d7a1f5c8e2b4d6a9f" >"${scratch}/work/notes.sh"
commit "feat: add notes"
if push push -q origin leaked; then
	fail "an authored secret must fail the hook"
fi
grep -qE '✗ (betterleaks|gitleaks)' "${scratch}/push.txt" || fail "a security step must be the one that fails"

echo "ok pre-push-upstream-merge"
