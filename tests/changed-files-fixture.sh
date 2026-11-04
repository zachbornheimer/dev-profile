#!/usr/bin/env bash
# dev-profile-changed-files hands a per-file step only the files this push
# introduces. A file is introduced when its content at the pushed tip differs
# from every base the push inherited: the ref's remote tip (advanced to the
# default branch's merge base when the branch moved onto a newer one, and the
# branch's published tip when the remote is unborn), the merge base with
# origin's default branch, and the published parents of any commit in the
# pushed range — the upstream line a fork branch merged in, however deep in
# the range the merge sits, which the push did not write. Without push refs
# the candidates pass through untouched; a push that introduces nothing must
# not run the step's tool at all.
set -euo pipefail

src="$(cd "$(dirname "$0")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
fail() {
	echo "FAIL: $*" >&2
	exit 1
}

export GIT_CONFIG_GLOBAL="${work}/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "${GIT_CONFIG_GLOBAL}" user.name fixture
git config --file "${GIT_CONFIG_GLOBAL}" user.email fixture@example.invalid
git config --file "${GIT_CONFIG_GLOBAL}" commit.gpgsign false

# The recording command stands in for a step's tool: it prints the files it
# was handed, so the fixture can assert exactly which candidates reached it.
cat >"${work}/record.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@"
EOF
chmod +x "${work}/record.sh"

repo="${work}/repo"
git init -q -b main "${repo}"
cd "${repo}"
printf 'main\n' >main.md
git add main.md
git commit -q -m main
git update-ref refs/remotes/origin/main HEAD

git switch -q -c upstream
printf 'upstream\n' >upstream.md
git add upstream.md
git commit -q -m upstream-file
git update-ref refs/remotes/upstream/main HEAD

git switch -q main
git switch -q -c topic
printf 'topic\n' >topic.txt
git add topic.txt
git commit -q -m topic-file
topic_tip="$(git rev-parse HEAD)"
git update-ref refs/remotes/origin/topic HEAD

git merge -q --no-edit upstream
merge="$(git rev-parse HEAD)"

gate() {
	"${src}/bin/dev-profile-changed-files" "${work}/record.sh" -- "$@" \
		>"${work}/passed" 2>"${work}/log"
}
push() { # <local_sha> <remote_sha> <candidate>...
	printf 'refs/heads/topic %s refs/heads/topic %s\n' "$1" "$2" >"${work}/refs"
	DEV_PROFILE_PUSH_REFS="${work}/refs" gate "${@:3}"
}

# A push of the merged branch hands the step its remote tip, the default
# branch's merge base, and the published parents of the merge: nothing is
# introduced, so the tool must not run at all.
push "${merge}" "${topic_tip}" main.md topic.txt upstream.md
if [ -s "${work}/passed" ]; then
	fail "a fully inherited push must run no tool: $(cat "${work}/passed")"
fi
grep -Eq '0 of 3 candidate file\(s\) introduced by this push.*skipped' "${work}/log" ||
	fail "the skip must be logged: $(cat "${work}/log")"

# An unborn remote falls back to the branch's own published tip; the push still
# introduces nothing.
push "${merge}" 0000000000000000000000000000000000000000 main.md topic.txt upstream.md
if [ -s "${work}/passed" ]; then
	fail "an unborn remote with a published tip must run no tool: $(cat "${work}/passed")"
fi

# A commit authored on top of the merge is the push's own work. The upstream
# file the mid-range merge carried in matches the published upstream line, so
# it is inherited however deep in the range the merge sits; only the authored
# file is introduced.
printf 'authored\n' >authored.md
git add authored.md
git commit -q -m authored
push "$(git rev-parse HEAD)" "${topic_tip}" main.md topic.txt upstream.md authored.md
printf 'authored.md\n' >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "only the authored file is introduced: $(cat "${work}/passed")"
fi
grep -Eq '1 of 4 candidate file\(s\) introduced by this push.*running' "${work}/log" ||
	fail "the run must be logged: $(cat "${work}/log")"

# A line the push re-carries: a second merge of an upstream line that has
# moved on — published on its own remote — still introduces nothing but the
# branch's authored file; a push must not re-answer for a line it re-carries.
git switch -q upstream
printf 'upstream2\n' >upstream2.md
git add upstream2.md
git commit -q -m upstream-file-2
git update-ref refs/remotes/upstream/main HEAD
git switch -q topic
git merge -q --no-edit upstream
push "$(git rev-parse HEAD)" "${topic_tip}" main.md topic.txt upstream.md upstream2.md authored.md
printf 'authored.md\n' >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "a re-carried upstream line must introduce nothing new: $(cat "${work}/passed")"
fi

# A push whose tip is already the remote tip introduces nothing.
push "$(git rev-parse HEAD)" "$(git rev-parse HEAD)" main.md topic.txt upstream.md authored.md
if [ -s "${work}/passed" ]; then
	fail "a tip already on the remote must run no tool: $(cat "${work}/passed")"
fi

# Without push refs (pre-commit, a direct run) every candidate passes through.
unset DEV_PROFILE_PUSH_REFS
gate main.md topic.txt upstream.md authored.md
printf 'authored.md\nmain.md\ntopic.txt\nupstream.md\n' | sort >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "without push refs every candidate must pass through: $(cat "${work}/passed")"
fi
grep -q 'no push refs' "${work}/log" ||
	fail "the pass-through must be logged: $(cat "${work}/log")"

# A step with no candidates exits 0 without running its tool.
DEV_PROFILE_PUSH_REFS="${work}/refs" gate
if [ -s "${work}/passed" ] || [ -s "${work}/log" ]; then
	fail "an empty candidate list must run no tool and log nothing"
fi

# The separator is required: without it nothing can run.
if "${src}/bin/dev-profile-changed-files" "${work}/record.sh" main.md \
	>"${work}/passed" 2>"${work}/log"; then
	fail "a command without the -- separator must be refused"
fi
grep -q 'usage:' "${work}/log" || fail "the refusal must explain the usage: $(cat "${work}/log")"

echo "ok changed-files fixture"
